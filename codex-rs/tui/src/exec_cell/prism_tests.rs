use super::*;
use crate::exec_cell::model::CommandOutput;
use crate::exec_cell::model::ExecCall;
use crate::history_cell::HistoryCell;
use codex_app_server_protocol::CommandExecutionSource;
use codex_protocol::parse_command::ParsedCommand;
use pretty_assertions::assert_eq;
use std::time::Duration;

#[test]
fn full_commands_are_colored_and_only_the_output_preview_is_folded() {
    let command = vec![
        "bash".into(),
        "-lc".into(),
        "cat -- ./some-long-input-file.txt".into(),
    ];
    let cell = ExecCell::new(
        ExecCall {
            call_id: "example".into(),
            command: command.clone(),
            parsed: vec![ParsedCommand::Read {
                cmd: "cat".into(),
                name: "some-long-input-file.txt".into(),
                path: "some-long-input-file.txt".into(),
            }],
            output: Some(CommandOutput::new(
                0,
                (0..12).map(|i| format!("output line {i}\n")).collect(),
            )),
            source: CommandExecutionSource::Agent,
            start_time: None,
            duration: Some(Duration::from_millis(12)),
            interaction_input: None,
        },
        /*animations_enabled*/ false,
    );
    let settings = Settings {
        enabled: true,
        output_preview_lines: 2,
        ..Settings::default()
    };
    let lines = display_lines(&cell, /*width*/ 72, &settings);
    let text = lines
        .iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>()
        .join("\n");
    insta::assert_snapshot!(text);
    assert_eq!(lines[0].style.fg, Some(ratatui::style::Color::Cyan));
    assert!(lines[1].spans.iter().any(|s| s.style.fg.is_some()));
    assert_eq!(cell.calls[0].command, command);
    let transcript = cell
        .transcript_lines(/*width*/ 100)
        .iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>()
        .join("\n");
    for i in 0..12 {
        assert!(transcript.contains(&format!("output line {i}")));
    }
    assert_eq!(
        display_lines(&cell, /*width*/ 0, &settings),
        Vec::<Line>::new()
    );
}
