use crate::model::*;
use crate::providers::ProviderError;
use base64::Engine;
use serde::Deserialize;
use std::path::PathBuf;

fn auth_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".codex/auth.json")
}

#[derive(Deserialize)]
struct Auth {
    tokens: Tokens,
}

#[derive(Deserialize)]
struct Tokens {
    access_token: String,
    account_id: String,
}

#[derive(Deserialize)]
struct UsageResponse {
    rate_limit: Option<RateLimit>,
}

#[derive(Deserialize)]
struct RateLimit {
    primary_window: Option<Window>,
    secondary_window: Option<Window>,
}

#[derive(Deserialize)]
struct Window {
    limit_window_seconds: f64,
    used_percent: Option<f64>,
    reset_at: Option<f64>,
    reset_after_seconds: Option<f64>,
}

fn load_credential() -> Result<(String, String), ProviderError> {
    let path = auth_path();
    let data = std::fs::read_to_string(&path).map_err(|_| ProviderError::NeedsAuth)?;
    let auth: Auth = serde_json::from_str(&data).map_err(|_| ProviderError::NeedsAuth)?;
    if auth.tokens.access_token.trim().is_empty() || auth.tokens.account_id.trim().is_empty() {
        return Err(ProviderError::NeedsAuth);
    }
    if let Some(exp) = jwt_exp(&auth.tokens.access_token) {
        let now = chrono::Utc::now().timestamp() as f64;
        if exp <= now {
            return Err(ProviderError::CredentialExpired);
        }
    }
    Ok((auth.tokens.access_token, auth.tokens.account_id))
}

fn jwt_exp(token: &str) -> Option<f64> {
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() < 2 {
        return None;
    }
    let mut payload = parts[1].replace('-', "+").replace('_', "/");
    while payload.len() % 4 != 0 {
        payload.push('=');
    }
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(payload)
        .ok()?;
    let value: serde_json::Value = serde_json::from_slice(&bytes).ok()?;
    value.get("exp")?.as_f64()
}

fn window_label(seconds: f64, fallback: &str) -> String {
    if seconds <= 0.0 {
        return if fallback == "primary" {
            "Current session".into()
        } else {
            "Longer window".into()
        };
    }
    let minutes = seconds / 60.0;
    if minutes < 60.0 {
        return format!("{}m limit", minutes as i64);
    }
    if minutes < 60.0 * 24.0 {
        return format!("{}h limit", (minutes / 60.0) as i64);
    }
    let days = (minutes / (60.0 * 24.0)).round() as i64;
    match days {
        7 => "Weekly limit".into(),
        30 => "Monthly limit".into(),
        _ => format!("{days}d limit"),
    }
}

pub async fn fetch() -> Result<ProviderSnapshot, ProviderError> {
    let (token, account_id) = load_credential()?;
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| ProviderError::Other(e.to_string()))?;

    let resp = client
        .get("https://chatgpt.com/backend-api/wham/usage")
        .header("Authorization", format!("Bearer {token}"))
        .header("ChatGPT-Account-Id", &account_id)
        .header("Accept", "application/json")
        .header("Cache-Control", "no-cache, no-store")
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
        .map_err(|_| ProviderError::BadResponse(0))?;

    let now = chrono::Utc::now();
    let mut windows = Vec::new();
    for (id, window) in [
        ("primary", body.rate_limit.as_ref().and_then(|r| r.primary_window.as_ref())),
        ("secondary", body.rate_limit.as_ref().and_then(|r| r.secondary_window.as_ref())),
    ] {
        let Some(window) = window else { continue };
        let Some(percent) = window.used_percent else {
            return Err(ProviderError::BadResponse(0));
        };
        let resets_at = window
            .reset_at
            .and_then(|t| chrono::DateTime::from_timestamp(t as i64, 0))
            .or_else(|| {
                window
                    .reset_after_seconds
                    .map(|s| now + chrono::Duration::seconds(s as i64))
            });
        windows.push(LimitWindow {
            id: id.into(),
            label: window_label(window.limit_window_seconds, id),
            used_fraction: Some(percent / 100.0),
            remaining: None,
            used: None,
            resets_at,
        });
    }

    if windows.is_empty() {
        return Err(ProviderError::NothingMetered(
            "Codex reported no usage windows".into(),
        ));
    }

    let headline = windows.first().map(|w| w.id.clone());
    Ok(ProviderSnapshot {
        id: "codex".into(),
        display_name: "Codex".into(),
        glyph: "openai".into(),
        fidelity: Fidelity::Official,
        status: ProviderStatus::Ok,
        windows,
        headline_id: headline,
    })
}
