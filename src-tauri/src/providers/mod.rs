pub mod claude;
pub mod codex;
pub mod cursor;
pub mod fixtures;

use crate::model::ProviderSnapshot;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ProviderError {
    #[error("needs auth")]
    NeedsAuth,
    #[error("access denied")]
    AccessDenied,
    #[error("credential expired")]
    CredentialExpired,
    #[error("nothing metered: {0}")]
    NothingMetered(String),
    #[error("bad response ({0})")]
    BadResponse(u16),
    #[error("{0}")]
    Other(String),
}

pub async fn fetch(id: &str) -> Result<ProviderSnapshot, ProviderError> {
    match id {
        "claude" => claude::fetch().await,
        "cursor" => cursor::fetch().await,
        "codex" => codex::fetch().await,
        _ => Err(ProviderError::Other(format!("unknown provider {id}"))),
    }
}
