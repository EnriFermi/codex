//! Full command text with a bounded output preview; Ctrl+T keeps upstream full transcript.

use super::model::ExecCell;
use super::render::OutputLinesParams;
use super::render::output_lines;
use crate::exec_command::escape_command;
use crate::prism::Settings;
use crate::prism::color_style;
use crate::render::highlight::highlight_bash_to_lines;
use crate::wrapping::RtOptions;
use crate::wrapping::adaptive_wrap_lines;
use ratatui::style::Modifier;
use ratatui::style::Stylize;
use ratatui::text::Line;

pub(super) fn display_lines(
    cell: &ExecCell,
    width: u16,
    settings: &Settings,
) -> Vec<Line<'static>> {
    if width == 0 {
        return Vec::new();
    }
    let mut lines = Vec::new();
    for call in cell.iter_calls() {
        let status = match &call.output {
            Some(output) if call.duration.is_some() => format!("exit {}", output.exit_code),
            _ => "running".to_string(),
        };
        lines.push(
            Line::from(format!("$ COMMAND · {status}").bold())
                .style(color_style(&settings.command_color)),
        );
        let command = highlight_bash_to_lines(&escape_command(&call.command));
        lines.extend(adaptive_wrap_lines(
            &command,
            RtOptions::new(width as usize)
                .initial_indent("  ".into())
                .subsequent_indent("  ".into()),
        ));
        if let Some(input) = &call.interaction_input
            && !input.is_empty()
        {
            lines.push(Line::from(format!("  stdin: {input:?}")));
        }
        if let Some(output) = &call.output {
            let preview = output_lines(
                Some(output),
                OutputLinesParams {
                    line_limit: settings.output_preview_lines,
                    only_err: false,
                    include_angle_pipe: false,
                    include_prefix: false,
                },
            );
            lines.push(Line::from("  OUTPUT · Ctrl+T to expand".dim()));
            let preview = preview
                .lines
                .into_iter()
                .map(|mut line| {
                    for span in &mut line.spans {
                        span.style = span.style.remove_modifier(Modifier::DIM);
                        if span.style.fg.is_none() {
                            span.style = span.style.patch(color_style(&settings.output_color));
                        }
                    }
                    line
                })
                .collect::<Vec<_>>();
            lines.extend(adaptive_wrap_lines(
                &preview,
                RtOptions::new(width as usize)
                    .initial_indent("  │ ".into())
                    .subsequent_indent("  │ ".into()),
            ));
        }
    }
    lines
}

#[cfg(test)]
#[path = "prism_tests.rs"]
mod tests;
