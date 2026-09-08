use crate::model::*;
use crate::providers::ProviderError;
use serde::Deserialize;
use std::path::PathBuf;

#[derive(Deserialize)]
struct Payload {
    #[serde(rename = "claudeAiOauth")]
    claude_ai_oauth: OAuth,
}

#[derive(Deserialize)]
struct OAuth {
    #[serde(rename = "accessToken")]
    access_token: String,
    #[serde(rename = "expiresAt")]
    expires_at: f64,
}

#[derive(Deserialize)]
struct UsageResponse {
    limits: Option<Vec<Limit>>,
    #[serde(rename = "fiveHour")]
    five_hour: Option<NamedWindow>,
    #[serde(rename = "sevenDay")]
    seven_day: Option<NamedWindow>,
}

#[derive(Deserialize)]
struct Limit {
    kind: String,
    percent: f64,
    #[serde(rename = "resetsAt")]
    resets_at: Option<chrono::DateTime<chrono::Utc>>,
}

#[derive(Deserialize)]
struct NamedWindow {
    utilization: f64,
    #[serde(rename = "resetsAt")]
    resets_at: Option<chrono::DateTime<chrono::Utc>>,
}

fn file_credential_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();
    if let Some(home) = dirs::home_dir() {
        paths.push(home.join(".claude/.credentials.json"));
        paths.push(home.join(".claude/credentials.json"));
        paths.push(home.join(".config/claude/credentials.json"));
    }
    paths
}

fn load_from_file() -> Result<String, ProviderError> {
    for path in file_credential_paths() {
        if !path.exists() {
            continue;
        }
        let text = std::fs::read_to_string(&path).map_err(|_| ProviderError::NeedsAuth)?;
        if let Ok(payload) = serde_json::from_str::<Payload>(&text) {
            let exp_ms = payload.claude_ai_oauth.expires_at;
            let now_ms = chrono::Utc::now().timestamp_millis() as f64;
            if exp_ms <= now_ms {
                return Err(ProviderError::CredentialExpired);
            }
            return Ok(payload.claude_ai_oauth.access_token);
        }
        // Some installs nest the oauth object one level deeper.
        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) {
            if let Some(oauth) = value.get("claudeAiOauth") {
                let token = oauth
                    .get("accessToken")
                    .and_then(|v| v.as_str())
                    .ok_or(ProviderError::NeedsAuth)?;
                return Ok(token.to_string());
            }
        }
    }
    Err(ProviderError::NeedsAuth)
}

async fn load_from_secret_service() -> Result<String, ProviderError> {
    #[cfg(feature = "keyring")]
    {
        let ss = secret_service::SecretService::new(secret_service::EncryptionType::Dh)
            .await
            .map_err(|_| ProviderError::NeedsAuth)?;
        let collection = ss
            .get_default_collection()
            .await
            .map_err(|_| ProviderError::NeedsAuth)?;
        let _ = collection.unlock().await;

        for service in ["Claude Code-credentials", "claude-code", "Claude Code"] {
            let items = collection
                .search_items(&[("service", service)])
                .await
                .unwrap_or_default();
            for item in items {
                let _ = item.unlock().await;
                if let Ok(secret) = item.get_secret().await {
                    let text = String::from_utf8_lossy(&secret);
                    if let Ok(payload) = serde_json::from_str::<Payload>(&text) {
                        return Ok(payload.claude_ai_oauth.access_token);
                    }
                    if text.contains("accessToken") {
                        if let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) {
                            if let Some(token) = value
                                .pointer("/claudeAiOauth/accessToken")
                                .and_then(|v| v.as_str())
                            {
                                return Ok(token.to_string());
                            }
                        }
                    }
                }
            }
        }
    }
    Err(ProviderError::NeedsAuth)
}

async fn load_token() -> Result<String, ProviderError> {
    match load_from_file() {
        Ok(token) => Ok(token),
        Err(_) => load_from_secret_service().await,
    }
}

fn label_for_kind(kind: &str) -> String {
    match kind {
        "session" => "Current session".into(),
        "weekly_all" => "All models".into(),
        "weekly_opus" => "Opus".into(),
        "weekly_sonnet" => "Sonnet".into(),
        other => other.replace("weekly_", "").replace('_', " "),
    }
}

fn to_windows(body: UsageResponse) -> Vec<LimitWindow> {
    let mut windows: Vec<LimitWindow> = body
        .limits
        .unwrap_or_default()
        .into_iter()
        .filter_map(|limit| {
            let resets_at = limit.resets_at?;
            Some(LimitWindow {
                id: limit.kind.clone(),
                label: label_for_kind(&limit.kind),
                used_fraction: Some(limit.percent / 100.0),
                remaining: None,
                used: None,
                resets_at: Some(resets_at),
            })
        })
        .collect();

    let mut merge = |window: Option<NamedWindow>, id: &str, label: &str| {
        if let Some(window) = window {
            if let Some(resets_at) = window.resets_at {
                if !windows.iter().any(|w| w.id == id) {
                    windows.push(LimitWindow {
                        id: id.into(),
                        label: label.into(),
                        used_fraction: Some(window.utilization / 100.0),
                        remaining: None,
                        used: None,
                        resets_at: Some(resets_at),
                    });
                }
            }
        }
    };
    merge(body.five_hour, "session", "Current session");
    merge(body.seven_day, "weekly_all", "All models");

    windows.sort_by_key(|w| match w.id.as_str() {
        "session" => 0,
        "weekly_all" => 1,
        _ => 2,
    });
    windows
}

pub async fn fetch() -> Result<ProviderSnapshot, ProviderError> {
    let token = load_token().await?;
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| ProviderError::Other(e.to_string()))?;

    let resp = client
        .get("https://api.anthropic.com/api/oauth/usage")
        .header("Authorization", format!("Bearer {token}"))
        .header("anthropic-beta", "oauth-2025-04-20")
        .send()
        .await
        .map_err(|e| ProviderError::Other(e.to_string()))?;

    let status = resp.status().as_u16();
    if status == 401 || status == 403 {
        return Err(ProviderError::NeedsAuth);
    }
    if !(200..300).contains(&status) {
        return Err(ProviderError::BadResponse(status));
    }

    let body: UsageResponse = resp
        .json()
        .await
        .map_err(|e| ProviderError::Other(e.to_string()))?;
    let windows = to_windows(body);
    if windows.is_empty() {
        return Err(ProviderError::NothingMetered(
            "Claude reported no usage windows".into(),
        ));
    }

    Ok(ProviderSnapshot {
        id: "claude".into(),
        display_name: "Claude".into(),
        glyph: "claude".into(),
        fidelity: Fidelity::Official,
        status: ProviderStatus::Ok,
        windows,
        headline_id: Some("session".into()),
    })
}
