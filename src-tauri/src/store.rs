use crate::model::*;
use crate::prefs::Preferences;
use crate::providers::{self, ProviderError};
use chrono::Utc;
use std::sync::Arc;
use tokio::sync::RwLock;

#[derive(Clone)]
pub struct UsageStore {
    inner: Arc<RwLock<Inner>>,
}

struct Inner {
    prefs: Preferences,
    snapshots: Vec<ProviderSnapshot>,
    demo: bool,
}

impl UsageStore {
    pub fn new(prefs: Preferences, demo: bool) -> Self {
        Self {
            inner: Arc::new(RwLock::new(Inner {
                prefs,
                snapshots: if demo {
                    providers::fixtures::snapshots()
                } else {
                    vec![]
                },
                demo,
            })),
        }
    }

    pub async fn snapshots(&self) -> Vec<serde_json::Value> {
        let guard = self.inner.read().await;
        guard
            .snapshots
            .iter()
            .map(|s| enrich_snapshot(s))
            .collect()
    }

    pub async fn prefs(&self) -> Preferences {
        self.inner.read().await.prefs.clone()
    }

    pub async fn set_prefs(&self, prefs: Preferences) -> Result<(), String> {
        prefs.save()?;
        let mut guard = self.inner.write().await;
        guard.prefs = prefs;
        Ok(())
    }

    pub async fn refresh_all(&self) {
        let (demo, prefs) = {
            let guard = self.inner.read().await;
            (guard.demo, guard.prefs.clone())
        };
        if demo {
            let snaps = providers::fixtures::snapshots();
            let mut guard = self.inner.write().await;
            guard.snapshots = snaps;
            return;
        }

        let mut next = Vec::new();
        for id in ["claude", "cursor", "codex"] {
            if !prefs.is_connected(id) {
                continue;
            }
            match providers::fetch(id).await {
                Ok(snap) => next.push(snap),
                Err(ProviderError::NeedsAuth) => next.push(needs_auth_stub(id)),
                Err(ProviderError::AccessDenied) => next.push(ProviderSnapshot {
                    id: id.into(),
                    display_name: display_name(id).into(),
                    glyph: glyph(id).into(),
                    fidelity: Fidelity::Official,
                    status: ProviderStatus::AccessDenied,
                    windows: vec![],
                    headline_id: None,
                }),
                Err(err) => {
                    tracing::warn!("provider {id} failed: {err}");
                    next.push(ProviderSnapshot {
                        id: id.into(),
                        display_name: display_name(id).into(),
                        glyph: glyph(id).into(),
                        fidelity: Fidelity::Official,
                        status: ProviderStatus::Error {
                            message: err.to_string(),
                        },
                        windows: vec![],
                        headline_id: None,
                    });
                }
            }
        }
        let mut guard = self.inner.write().await;
        guard.snapshots = next;
    }

    pub async fn refresh_one(&self, id: &str) {
        let (demo, connected) = {
            let guard = self.inner.read().await;
            (guard.demo, guard.prefs.is_connected(id))
        };
        if demo || !connected {
            return;
        }
        match providers::fetch(id).await {
            Ok(snap) => {
                let mut guard = self.inner.write().await;
                if let Some(slot) = guard.snapshots.iter_mut().find(|s| s.id == id) {
                    *slot = snap;
                } else {
                    guard.snapshots.push(snap);
                }
            }
            Err(err) => tracing::warn!("refresh {id}: {err}"),
        }
    }
}

fn enrich_snapshot(s: &ProviderSnapshot) -> serde_json::Value {
    let now = Utc::now();
    let used = s.used_fraction();
    let color = used.map(ProviderSnapshot::band_color).unwrap_or("#303030");
    let windows: Vec<serde_json::Value> = s
        .windows
        .iter()
        .map(|w| {
            serde_json::json!({
                "id": w.id,
                "label": w.label,
                "usedFraction": w.used_fraction,
                "remaining": w.remaining,
                "used": w.used,
                "resetsAt": w.resets_at,
                "summary": w.summary(),
                "resetCopy": w.resets_at.map(|t| reset_copy(t, now)),
                "bandColor": w.used_fraction.map(ProviderSnapshot::band_color),
            })
        })
        .collect();

    serde_json::json!({
        "id": s.id,
        "displayName": s.display_name,
        "glyph": s.glyph,
        "fidelity": s.fidelity,
        "status": s.status,
        "windows": windows,
        "headlineId": s.headline_id,
        "headlineText": s.headline_text(),
        "usedFraction": used,
        "bandColor": color,
        "hasReading": !s.windows.is_empty(),
        "stale": matches!(s.status, ProviderStatus::Stale { .. }),
    })
}

fn display_name(id: &str) -> &'static str {
    match id {
        "claude" => "Claude",
        "cursor" => "Cursor",
        "codex" => "Codex",
        _ => id,
    }
}

fn glyph(id: &str) -> &'static str {
    match id {
        "claude" => "claude",
        "cursor" => "cursor",
        "codex" => "openai",
        _ => "third",
    }
}

fn needs_auth_stub(id: &str) -> ProviderSnapshot {
    ProviderSnapshot {
        id: id.into(),
        display_name: display_name(id).into(),
        glyph: glyph(id).into(),
        fidelity: Fidelity::Official,
        status: ProviderStatus::NeedsAuth,
        windows: vec![],
        headline_id: None,
    }
}
