use std::sync::Arc;

use axum::{
    Json,
    extract::{Request, State},
    http::StatusCode,
    middleware::Next,
    response::Response,
};

pub const TOKEN_HEADER: &str = "x-caloron-token";
pub const TOKEN_ENV: &str = "CALORON_SHELL_TOKEN";

#[derive(Clone)]
pub struct AuthConfig {
    /// None = auth disabled (only valid in debug builds).
    expected: Option<Arc<String>>,
}

impl AuthConfig {
    pub fn from_env() -> anyhow::Result<Self> {
        let raw = std::env::var(TOKEN_ENV).ok().filter(|s| !s.is_empty());
        match raw {
            Some(t) => Ok(Self {
                expected: Some(Arc::new(t)),
            }),
            None => {
                if cfg!(debug_assertions) {
                    tracing::warn!(
                        "{TOKEN_ENV} is unset; auth is DISABLED (debug build only — release builds refuse to start)"
                    );
                    Ok(Self { expected: None })
                } else {
                    anyhow::bail!("{TOKEN_ENV} must be set to a non-empty value in release builds");
                }
            }
        }
    }
}

pub async fn require_token(
    State(auth): State<AuthConfig>,
    req: Request,
    next: Next,
) -> Result<Response, (StatusCode, Json<serde_json::Value>)> {
    let Some(expected) = &auth.expected else {
        return Ok(next.run(req).await);
    };

    let provided = req
        .headers()
        .get(TOKEN_HEADER)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if constant_time_eq(expected.as_bytes(), provided.as_bytes()) {
        Ok(next.run(req).await)
    } else {
        Err((
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "ok": false,
                "error": format!("missing or invalid {TOKEN_HEADER} header")
            })),
        ))
    }
}

/// Constant-time byte comparison. Returns false for length mismatch (length
/// itself is not a secret here — tokens are fixed-length per deployment).
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff: u8 = 0;
    for (x, y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn constant_time_eq_matches() {
        assert!(constant_time_eq(b"secret", b"secret"));
        assert!(constant_time_eq(b"", b""));
    }

    #[test]
    fn constant_time_eq_rejects_mismatch() {
        assert!(!constant_time_eq(b"secret", b"secreT"));
        assert!(!constant_time_eq(b"secret", b"secre"));
        assert!(!constant_time_eq(b"secret", b"secrets"));
        assert!(!constant_time_eq(b"", b"x"));
    }
}
