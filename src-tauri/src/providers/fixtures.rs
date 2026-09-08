use crate::model::*;
use chrono::{Duration, TimeZone, Utc};

pub fn snapshots() -> Vec<ProviderSnapshot> {
    let now = Utc::now();
    let session_reset = now + Duration::minutes(51);
    let tomorrow = (now + Duration::days(1)).date_naive();
    let midnight = Utc.from_utc_datetime(
        &tomorrow
            .and_hms_opt(0, 0, 0)
            .unwrap_or_else(|| now.naive_utc()),
    );

    vec![
        ProviderSnapshot {
            id: "claude".into(),
            display_name: "Claude".into(),
            glyph: "claude".into(),
            fidelity: Fidelity::Derived,
            status: ProviderStatus::Ok,
            windows: vec![
                LimitWindow {
                    id: "claude.session".into(),
                    label: "Current session".into(),
                    used_fraction: Some(0.73),
                    remaining: None,
                    used: None,
                    resets_at: Some(session_reset),
                },
                LimitWindow {
                    id: "claude.all".into(),
                    label: "All models".into(),
                    used_fraction: Some(0.07),
                    remaining: None,
                    used: None,
                    resets_at: Some(midnight),
                },
            ],
            headline_id: Some("claude.session".into()),
        },
        ProviderSnapshot {
            id: "codex".into(),
            display_name: "Codex".into(),
            glyph: "openai".into(),
            fidelity: Fidelity::Manual,
            status: ProviderStatus::Ok,
            windows: vec![LimitWindow {
                id: "openai.session".into(),
                label: "Current session".into(),
                used_fraction: Some(0.21),
                remaining: None,
                used: None,
                resets_at: Some(now + Duration::hours(3)),
            }],
            headline_id: Some("openai.session".into()),
        },
        ProviderSnapshot {
            id: "cursor".into(),
            display_name: "Cursor".into(),
            glyph: "cursor".into(),
            fidelity: Fidelity::Manual,
            status: ProviderStatus::Ok,
            windows: vec![LimitWindow {
                id: "third.daily".into(),
                label: "Included usage".into(),
                used_fraction: Some(0.52),
                remaining: None,
                used: None,
                resets_at: Some(midnight),
            }],
            headline_id: Some("third.daily".into()),
        },
    ]
}
