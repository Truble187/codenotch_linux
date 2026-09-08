use crate::model::*;
use crate::providers::ProviderError;
use rusqlite::Connection;
use serde_json::Value;
use std::path::PathBuf;

fn store_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Cursor/User/globalStorage/state.vscdb")
}

fn load_credentials() -> Result<(String, String), ProviderError> {
    let path = store_path();
    if !path.exists() {
        return Err(ProviderError::NeedsAuth);
    }
    let conn = Connection::open_with_flags(
        &path,
        rusqlite::OpenFlags::SQLITE_OPEN_READ_ONLY | rusqlite::OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|_| ProviderError::NeedsAuth)?;

    let token: String = conn
        .query_row(
            "SELECT value FROM ItemTable WHERE key = ?1",
            ["cursorAuth/accessToken"],
            |row| row.get(0),
        )
        .map_err(|_| ProviderError::NeedsAuth)?;
    let account: String = conn
        .query_row(
            "SELECT value FROM ItemTable WHERE key = ?1",
            ["cursorAuth/stripeMembershipAuthId"],
            |row| row.get(0),
        )
        .map_err(|_| ProviderError::NeedsAuth)?;

    if token.is_empty() || account.is_empty() {
        return Err(ProviderError::NeedsAuth);
    }
    Ok((account, token))
}

fn percent(v: &Value) -> Option<f64> {
    v.as_f64()
        .or_else(|| v.as_i64().map(|i| i as f64))
        .map(|n| n / 100.0)
}

fn parse_windows(root: &Value) -> Result<Vec<LimitWindow>, ProviderError> {
    let resets_at = root
        .get("billingCycleEnd")
        .and_then(|v| v.as_str())
        .and_then(|s| chrono::DateTime::parse_from_rfc3339(s).ok())
        .map(|d| d.with_timezone(&chrono::Utc));

    let plan = root
        .pointer("/individualUsage/plan")
        .cloned()
        .unwrap_or(Value::Null);

    let mut windows = Vec::new();
    let cursor_models = percent(&plan["autoPercentUsed"]);
    if let Some(total) = cursor_models.or_else(|| percent(&plan["totalPercentUsed"])) {
        windows.push(LimitWindow {
            id: "included".into(),
            label: if cursor_models.is_some() {
                "Cursor Models"
            } else {
                "Included usage"
            }
            .into(),
            used_fraction: Some(total),
            remaining: None,
            used: None,
            resets_at,
        });
    }
    if let Some(api) = percent(&plan["apiPercentUsed"]) {
        windows.push(LimitWindow {
            id: "api".into(),
            label: "Other Models".into(),
            used_fraction: Some(api),
            remaining: None,
            used: None,
            resets_at,
        });
    }

    if let Some(on_demand) = root.pointer("/individualUsage/onDemand") {
        if on_demand.get("enabled").and_then(|v| v.as_bool()) == Some(true) {
            let limit = on_demand
                .get("limit")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            let used = on_demand
                .get("used")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0);
            if limit > 0.0 {
                windows.push(LimitWindow {
                    id: "on_demand".into(),
                    label: "On demand".into(),
                    used_fraction: Some(used / limit),
                    remaining: None,
                    used: None,
                    resets_at,
                });
            }
        }
    }

    if !windows.is_empty() {
        return Ok(windows);
    }

    let membership = root
        .get("membershipType")
        .and_then(|v| v.as_str())
        .unwrap_or("this");
    if root.get("isUnlimited").and_then(|v| v.as_bool()) == Some(true) {
        return Err(ProviderError::NothingMetered(format!(
            "Unlimited on the {membership} plan — nothing to meter"
        )));
    }
    Err(ProviderError::NothingMetered(format!(
        "The {membership} plan has nothing for Cursor to meter yet"
    )))
}

pub async fn fetch() -> Result<ProviderSnapshot, ProviderError> {
    let (account, token) = load_credentials()?;
    let cookie = format!("WorkosCursorSessionToken={account}::{token}");

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| ProviderError::Other(e.to_string()))?;

    let resp = client
        .get("https://cursor.com/api/usage-summary")
        .header("Cookie", cookie)
        .header("Accept", "application/json")
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

    let body: Value = resp
        .json()
        .await
        .map_err(|e| ProviderError::Other(e.to_string()))?;
    let windows = parse_windows(&body)?;

    Ok(ProviderSnapshot {
        id: "cursor".into(),
        display_name: "Cursor".into(),
        glyph: "cursor".into(),
        fidelity: Fidelity::Official,
        status: ProviderStatus::Ok,
        windows,
        headline_id: Some("included".into()),
    })
}
