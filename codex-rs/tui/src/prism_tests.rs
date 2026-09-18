use super::*;
use pretty_assertions::assert_eq;

#[test]
fn appearance_parses_and_rejects_invalid_values() {
    let settings = parse_settings("reasoning_color = '#c4a7e7'\noutput_preview_lines = 8").unwrap();
    assert_eq!(settings.output_preview_lines, 8);
    assert_eq!(
        color_style(&settings.reasoning_color).fg,
        Some(crate::terminal_palette::rgb_color((196, 167, 231)))
    );
    for invalid in [
        "reasoning_color = 'not-a-color'",
        "output_preview_lines = 1001",
        "sandbox = 'disabled'",
    ] {
        assert!(parse_settings(invalid).is_err(), "{invalid}");
    }
}
