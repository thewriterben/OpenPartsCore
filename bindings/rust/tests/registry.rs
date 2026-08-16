//! Tests for the generated binding.
//!
//! These pin the behaviour ADR-0004 exists to describe: a board is not a USB
//! identity, so identification is a match returning candidates.

use openpartscore::{by_id, candidates_for_usb, in_namespace, with_capability, Namespace, PARTS};

#[test]
fn registry_is_not_empty_and_every_entry_is_cited() {
    assert!(PARTS.len() >= 100, "expected the full registry, got {}", PARTS.len());
    for part in PARTS {
        assert!(
            !part.citation.trim().is_empty(),
            "{} has no citation; uncited entries must not reach the binding",
            part.id
        );
        assert!(part.id.starts_with(part.namespace.as_str()));
    }
}

#[test]
fn lookup_by_id_finds_a_known_board() {
    let part = by_id("boards/esp32-s3").expect("boards/esp32-s3 should exist");
    assert_eq!(part.namespace, Namespace::Boards);
    assert!(part.capabilities.contains(&"gpio"));
}

#[test]
fn one_board_can_hold_several_usb_identities() {
    // esp32-s3 enumerates through native USB, CP2102 and CH343.
    let part = by_id("boards/esp32-s3").unwrap();
    assert!(
        part.usb_ids.len() >= 3,
        "expected several identities, got {:?}",
        part.usb_ids
    );
}

#[test]
fn one_usb_identity_can_belong_to_many_boards() {
    // 0x303a:0x1001 is every native-USB ESP32 part. A lookup returning one
    // answer here would be wrong, which is the whole point of ADR-0004.
    let candidates: Vec<_> = candidates_for_usb(0x303a, 0x1001).collect();
    assert!(
        candidates.len() > 5,
        "expected many candidates for the shared ESP32 id, got {}",
        candidates.len()
    );
}

#[test]
fn unknown_usb_identity_yields_no_candidates() {
    assert_eq!(candidates_for_usb(0xdead, 0xbeef).count(), 0);
}

#[test]
fn capability_and_namespace_indexes_agree_with_the_data() {
    let camera: Vec<_> = with_capability("camera_capture").collect();
    assert!(!camera.is_empty(), "expected at least one camera-capable part");
    for part in &camera {
        assert!(part.capabilities.contains(&"camera_capture"));
    }

    let boards = in_namespace(Namespace::Boards).count();
    let electronic = in_namespace(Namespace::Electronic).count();
    assert!(boards >= 60 && electronic >= 30, "{boards} boards, {electronic} electronic");
    assert_eq!(
        boards + electronic + in_namespace(Namespace::Mechanical).count()
            + in_namespace(Namespace::Material).count(),
        PARTS.len()
    );
}

#[test]
fn attributes_json_is_present_for_boards() {
    let part = by_id("boards/esp32-s3").unwrap();
    assert!(part.attributes_json.contains("usb_ids"));
}
