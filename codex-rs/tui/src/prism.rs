//! Presentation-only customization. Command dispatch, permissions and protocol stay upstream.

use ratatui::style::Color;
use ratatui::style::Style;
use serde::Deserialize;
use std::sync::OnceLock;

#[derive(Clone, Debug, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct Settings {
    #[serde(skip)]
    pub(crate) enabled: bool,
    pub(crate) full_commands: bool,
    pub(crate) reasoning_in_chat: bool,
    pub(crate) math: bool,
    pub(crate) output_preview_lines: usize,
    pub(crate) reasoning_color: String,
    pub(crate) command_color: String,
    pub(crate) output_color: String,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            enabled: false,
            full_commands: true,
            reasoning_in_chat: true,
            math: true,
            output_preview_lines: 4,
            reasoning_color: "magenta".into(),
            command_color: "cyan".into(),
            output_color: "gray".into(),
        }
    }
}

static SETTINGS: OnceLock<(Settings, Option<String>)> = OnceLock::new();

fn loaded() -> &'static (Settings, Option<String>) {
    SETTINGS.get_or_init(|| {
        let enabled = std::env::var("CODEX_PRISM").as_deref() == Ok("1");
        if !enabled {
            return (Settings::default(), None);
        }
        let result = std::env::var_os("CODEX_PRISM_CONFIG")
            .map(std::path::PathBuf::from)
            .filter(|path| path.exists())
            .map(|path| {
                std::fs::read_to_string(&path)
                    .map_err(|err| format!("{}: {err}", path.display()))
                    .and_then(|source| parse_settings(&source))
            })
            .unwrap_or_else(|| Ok(Settings::default()));
        let (mut settings, warning) = match result {
            Ok(settings) => (settings, None),
            Err(err) => (
                Settings::default(),
                Some(format!("Prism appearance: {err}. Using defaults.")),
            ),
        };
        settings.enabled = true;
        (settings, warning)
    })
}

pub(crate) fn settings() -> &'static Settings {
    &loaded().0
}

pub(crate) fn startup_warning() -> Option<String> {
    loaded().1.clone()
}

fn parse_settings(source: &str) -> Result<Settings, String> {
    let settings: Settings = toml::from_str(source).map_err(|err| err.to_string())?;
    if settings.output_preview_lines > 1000 {
        return Err("output_preview_lines must be between 0 and 1000".into());
    }
    for color in [
        &settings.reasoning_color,
        &settings.command_color,
        &settings.output_color,
    ] {
        color
            .parse::<Color>()
            .map_err(|_| format!("invalid color: {color}"))?;
    }
    Ok(settings)
}

pub(crate) fn color_style(color: &str) -> Style {
    Style::default().fg(color.parse().unwrap_or(Color::Reset))
}

#[cfg(test)]
#[path = "prism_tests.rs"]
mod tests;
