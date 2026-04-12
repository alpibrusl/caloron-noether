use chrono::{DateTime, Utc};
use std::collections::HashMap;

/// In-memory heartbeat store with async KV persistence via Noether CLI.
pub struct HeartbeatStore {
    entries: HashMap<String, HeartbeatEntry>,
}

#[allow(dead_code)]
struct HeartbeatEntry {
    sprint_id: String,
    last_heartbeat: DateTime<Utc>,
    status: Option<String>,
}

impl HeartbeatStore {
    pub fn new() -> Self {
        Self {
            entries: HashMap::new(),
        }
    }

    pub fn record(&mut self, agent_id: &str, sprint_id: &str, status: Option<&str>) {
        let now = Utc::now();

        self.entries.insert(
            agent_id.to_string(),
            HeartbeatEntry {
                sprint_id: sprint_id.to_string(),
                last_heartbeat: now,
                status: status.map(|s| s.to_string()),
            },
        );

        // Persist to Noether KV store (fire and forget)
        let key = format!("caloron:{sprint_id}:agent:{agent_id}:last_heartbeat");
        let value = now.to_rfc3339();
        tokio::spawn(async move {
            let _ = write_kv(&key, &value).await;
        });
    }

    pub fn last_heartbeat(&self, agent_id: &str) -> Option<DateTime<Utc>> {
        self.entries.get(agent_id).map(|e| e.last_heartbeat)
    }
}

/// Write a value to the Noether KV store via the `noether` CLI.
/// Uses kv_set stage (ID: 9d885082) through a minimal inline graph.
async fn write_kv(key: &str, value: &str) -> anyhow::Result<()> {
    let input = serde_json::json!({
        "key": key,
        "value": value
    });

    // Call noether's kv_set directly via stage execution
    // The stage ID 9d885082 = "Store a JSON value under a key in the persistent key-value store"
    let graph = serde_json::json!({
        "description": "KV write",
        "version": "0.1.0",
        "root": { "op": "Stage", "id": "9d885082" }
    });

    let graph_str = graph.to_string();
    let input_str = input.to_string();

    // Write temp graph file (noether run needs a file path)
    let graph_path = format!("/tmp/caloron-kv-write-{}.json", std::process::id());
    tokio::fs::write(&graph_path, &graph_str).await?;

    let output = tokio::process::Command::new("noether")
        .args(["run", &graph_path, "--input", &input_str])
        .output()
        .await?;

    // Clean up temp file
    let _ = tokio::fs::remove_file(&graph_path).await;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        tracing::debug!(key, stderr = %stderr, "KV write via noether failed (non-fatal)");
    }

    Ok(())
}
