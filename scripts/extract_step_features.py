#!/usr/bin/env python3
"""Census of the named components in a vendor STEP, in the STEP's own frame (ADR-0007).

    uv run --python 3.12 --with cadquery-ocp==7.9.3.1.1 scripts/extract_step_features.py <file.step> [--out census.json]

A board's STEP says where every connector, switch and IC sits, but only as
geometry. The outline alone is what two camera mounts were cut from, and both
failed on things the outline does not contain: v0.1 hit the JST connectors,
v0.2 walled off the USB-C port. This script turns the STEP's named solids into
the per-component boxes that `features` entries are built from, so a feature's
position is read from the vendor's model rather than typed in.

It is run by hand, once per board revision, like ingest_obc.py; its output is
reviewed and the chosen components are copied into the entry's `features`
block with the census's sha256 as their source. Nothing in CI runs it: it
needs OCCT, and the registry deliberately has no heavy dependencies.

Output is deterministic for a given file and OCCT version: components are
sorted by name then position, and every coordinate is rounded to 0.001 mm.
Boxes are BRepBndLib::AddOptimal on the exact geometry (no triangulation, no
shape tolerance), with the component's full assembly location applied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool


def r3(v: float) -> float:
    # -0.0 and 0.0 must serialise identically or two runs differ by a sign.
    out = round(v, 3)
    return 0.0 if out == 0 else out


def label_name(label: TDF_Label) -> str:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return ""


def meaningful(name: str) -> str:
    """'' for names that identify nothing: XCAF placeholders and bare NAUO ids."""
    if not name or name.startswith("=>") or name.isdigit():
        return ""
    return name


def bbox(shape) -> list[float] | None:
    """None for a shape with no geometry (EasyEDA emits empty compounds)."""
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        return None
    return [r3(v) for v in box.Get()]


def census(path: str) -> dict:
    raw = open(path, "rb").read()
    doc = TDocStd_Document(TCollection_ExtendedString("odc-census"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise SystemExit(f"{path}: STEP read failed")
    if not reader.Transfer(doc):
        raise SystemExit(f"{path}: STEP transfer failed")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    # One entry per placed component instance; a multi-body part's bodies are
    # unioned into one box, because a fixture has to clear all of them.
    instances: dict[int, dict] = {}
    empty: list[str] = []
    counter = [0]

    def walk(label: TDF_Label, loc: TopLoc_Location, inherited: str, inst: int) -> None:
        if tool.IsAssembly_s(label):
            children = TDF_LabelSequence()
            tool.GetComponents_s(label, children, False)
            for i in range(1, children.Length() + 1):
                child = children.Value(i)
                child_loc = loc.Multiplied(tool.GetLocation_s(child))
                referred = TDF_Label()
                if tool.GetReferredShape_s(child, referred):
                    # The outermost name below the root wins. EasyEDA names
                    # each placed component's product '<prefix>-<refdes>-
                    # <footprint>'; a multi-body part (USB1, CN1, FPC1, ...)
                    # is an assembly of sub-products all called 'COMPOUND',
                    # and letting those override would erase the refdes.
                    # Instance labels carry a NAUO id or an XCAF placeholder
                    # '=>[0:1:1:n]' and are used only as a last resort.
                    name = (inherited or meaningful(label_name(referred))
                            or meaningful(label_name(child)))
                    child_inst = inst
                    if not inherited:
                        counter[0] += 1
                        child_inst = counter[0]
                    walk(referred, child_loc, name, child_inst)
            return
        shape = tool.GetShape_s(label)
        if shape.IsNull():
            return
        name = inherited or label_name(label)
        b = bbox(shape.Moved(loc))
        if b is None:
            empty.append(name)
            return
        if inst not in instances:
            instances[inst] = {"name": name, "bodies": 0,
                               "min_mm": b[0:3], "max_mm": b[3:6]}
        e = instances[inst]
        e["bodies"] += 1
        e["min_mm"] = [min(e["min_mm"][k], b[k]) for k in range(3)]
        e["max_mm"] = [max(e["max_mm"][k], b[k + 3]) for k in range(3)]

    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    for i in range(1, roots.Length() + 1):
        root = roots.Value(i)
        # The root's own name is the board, which would shadow every refdes.
        counter[0] += 1
        walk(root, TopLoc_Location(), "", counter[0])

    components = sorted(instances.values(),
                        key=lambda c: (c["name"], c["min_mm"], c["max_mm"]))
    return {
        "file": path.replace("\\", "/").rsplit("/", 1)[-1],
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "declared_unit": Interface_Static.CVal_s("xstep.cascade.unit"),
        "method": "STEPCAFControl_Reader; one box per placed component instance, the union of "
                  "its bodies with the full assembly location applied; "
                  "BRepBndLib::AddOptimal(useTriangulation=False, useShapeTolerance=False); "
                  "rounded to 0.001 mm",
        "empty_shapes": sorted(empty),
        "components": components,
    }


KIND_BY_PREFIX = (
    # Longest prefixes first: "CARD" must not be read as "C" (a capacitor).
    ("CARD", "card_slot"), ("USB", "connector"), ("FPC", "connector"),
    ("CN", "connector"), ("RF", "antenna"), ("SW", "switch"), ("KEY", "switch"),
    ("J", "connector"),
)
ACCESS_KINDS = {"connector", "switch", "card_slot", "antenna", "optic"}
# Zero-thickness artwork, not material: silkscreen and copper layers.
NOT_MATERIAL = ("TopSilk", "BottomSilk", "TopTrack", "BottomTrack")


def draft_items(result: dict) -> list[dict]:
    """Mechanical first draft of `features.items` from a census.

    Every access block comes out unknown (null), because nothing in the
    geometry says which way a plug goes in with certainty; a reviewer fills
    in what they can justify and leaves the rest null. The draft is the
    starting point for review, not an entry.
    """
    groups: dict[str, list[dict]] = {}
    for c in result["components"]:
        groups.setdefault(c["name"], []).append(c)
    items: list[dict] = []
    for name in sorted(groups):
        parts = name.split("-", 2)
        refdes = parts[1] if len(parts) > 1 else name
        if refdes in NOT_MATERIAL:
            continue
        letters = "".join(ch for ch in refdes if ch.isalpha())
        kind = "board" if refdes == "Board" else next(
            (k for p, k in KIND_BY_PREFIX if letters.startswith(p)), "component")
        members = groups[name]
        for n, c in enumerate(members, start=1):
            if any(c["max_mm"][k] <= c["min_mm"][k] for k in range(3)):
                continue
            shared = len(members) > 1
            item = {
                "id": f"{refdes}/{n}" if shared else refdes,
                "kind": kind,
                "box_mm": {"min_mm": c["min_mm"], "max_mm": c["max_mm"]},
                "source": f"step:{name}" + (
                    f" (instance {n} of {len(members)}: EasyEDA names a shared product after "
                    "one of its instances, so this refdes identifies the footprint, not the part)"
                    if shared else ""),
            }
            if kind in ACCESS_KINDS:
                item["access"] = {"direction": None, "depth_mm": None,
                                  "source": "TODO(source): not established"}
            items.append(item)
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("step")
    ap.add_argument("--out")
    ap.add_argument("--items", action="store_true",
                    help="emit a draft features.items list instead of the raw census")
    args = ap.parse_args()
    result = census(args.step)
    if args.items:
        result = {"file": result["file"], "sha256": result["sha256"],
                  "items": draft_items(result)}
    text = json.dumps(result, indent=1, sort_keys=False) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        n = len(result.get("components") or result.get("items") or [])
        print(f"{n} {'items' if args.items else 'components'} -> {args.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
