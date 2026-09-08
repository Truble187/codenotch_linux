use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub enum NotchVisibility {
    AlwaysShow,
    OnHover,
    Hidden,
}

impl Default for NotchVisibility {
    fn default() -> Self {
        Self::OnHover
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub enum NotchEdge {
    Right,
    Left,
    Top,
    Bottom,
}

impl Default for NotchEdge {
    fn default() -> Self {
        Self::Right
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Preferences {
    pub disconnected_providers: Vec<String>,
    pub notch_visibility: NotchVisibility,
    pub notch_edge: NotchEdge,
    pub launch_at_login: bool,
}

impl Default for Preferences {
    fn default() -> Self {
        Self {
            disconnected_providers: vec![],
            notch_visibility: NotchVisibility::OnHover,
            notch_edge: NotchEdge::Right,
            launch_at_login: false,
        }
    }
}

impl Preferences {
    fn path() -> PathBuf {
        dirs::config_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join("codenotch")
            .join("preferences.json")
    }

    pub fn load() -> Self {
        let path = Self::path();
        match fs::read_to_string(&path) {
            Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
            Err(_) => Self::default(),
        }
    }

    pub fn save(&self) -> Result<(), String> {
        let path = Self::path();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let text = serde_json::to_string_pretty(self).map_err(|e| e.to_string())?;
        fs::write(path, text).map_err(|e| e.to_string())
    }

    pub fn is_connected(&self, id: &str) -> bool {
        !self.disconnected_providers.iter().any(|p| p == id)
    }

    pub fn set_autostart(&mut self, enabled: bool) -> Result<(), String> {
        self.launch_at_login = enabled;
        let autostart_dir = dirs::config_dir()
            .ok_or_else(|| "no config dir".to_string())?
            .join("autostart");
        let desktop = autostart_dir.join("codenotch.desktop");
        if enabled {
            fs::create_dir_all(&autostart_dir).map_err(|e| e.to_string())?;
            let exec = std::env::current_exe().map_err(|e| e.to_string())?;
            let content = format!(
                "[Desktop Entry]\nType=Application\nName=Codenotch\nComment=Coding assistant usage notch\nExec={}\nIcon=codenotch\nTerminal=false\nX-GNOME-Autostart-enabled=true\n",
                exec.display()
            );
            fs::write(desktop, content).map_err(|e| e.to_string())?;
        } else if desktop.exists() {
            fs::remove_file(desktop).map_err(|e| e.to_string())?;
        }
        Ok(())
    }
}
