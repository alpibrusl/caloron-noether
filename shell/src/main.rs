mod heartbeat_server;
mod spawner;

use axum::{
    Json, Router,
    extract::State,
    routing::{get, post},
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::Mutex;

use heartbeat_server::HeartbeatStore;
use spawner::AgentSpawner;

/// Shared application state.
struct AppState {
    heartbeats: HeartbeatStore,
    spawner: AgentSpawner,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_env("CALORON_LOG_LEVEL")
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let port: u16 = std::env::var("CALORON_SHELL_PORT")
        .unwrap_or_else(|_| "7710".into())
        .parse()
        .unwrap_or(7710);

    let state = Arc::new(Mutex::new(AppState {
        heartbeats: HeartbeatStore::new(),
        spawner: AgentSpawner::new(),
    }));

    let app = Router::new()
        .route("/heartbeat", post(handle_heartbeat))
        .route("/spawn", post(handle_spawn))
        .route("/status", get(handle_status))
        .route("/health", get(handle_health))
        .with_state(state);

    let addr = format!("127.0.0.1:{port}");
    tracing::info!(addr, "caloron-shell listening");

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app).await?;

    Ok(())
}

// === Request/Response types ===

#[derive(Deserialize)]
#[allow(dead_code)]
struct HeartbeatRequest {
    agent_id: String,
    sprint_id: String,
    #[serde(default)]
    status: Option<String>,
    #[serde(default)]
    tokens_used: Option<u64>,
}

#[derive(Deserialize)]
struct SpawnRequest {
    sprint_id: String,
    task_id: String,
    agent_id: String,
    repo: String,
    #[serde(default = "default_worktree_base")]
    worktree_base: String,
}

fn default_worktree_base() -> String {
    ".caloron/worktrees".into()
}

#[derive(Serialize)]
struct OkResponse {
    ok: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pid: Option<u32>,
}

#[derive(Serialize)]
struct StatusResponse {
    agents: Vec<AgentInfo>,
}

#[derive(Serialize)]
struct AgentInfo {
    agent_id: String,
    sprint_id: String,
    pid: u32,
    alive: bool,
    last_heartbeat: Option<String>,
}

// === Handlers ===

async fn handle_heartbeat(
    State(state): State<Arc<Mutex<AppState>>>,
    Json(req): Json<HeartbeatRequest>,
) -> Json<OkResponse> {
    let mut state = state.lock().await;
    state
        .heartbeats
        .record(&req.agent_id, &req.sprint_id, req.status.as_deref());

    tracing::trace!(
        agent_id = req.agent_id,
        sprint_id = req.sprint_id,
        "Heartbeat received"
    );

    Json(OkResponse {
        ok: true,
        pid: None,
    })
}

async fn handle_spawn(
    State(state): State<Arc<Mutex<AppState>>>,
    Json(req): Json<SpawnRequest>,
) -> Json<serde_json::Value> {
    let mut state = state.lock().await;

    match state
        .spawner
        .spawn(
            &req.sprint_id,
            &req.task_id,
            &req.agent_id,
            &req.repo,
            &req.worktree_base,
        )
        .await
    {
        Ok(pid) => {
            tracing::info!(
                agent_id = req.agent_id,
                task_id = req.task_id,
                pid,
                "Agent spawned"
            );
            Json(serde_json::json!({ "ok": true, "pid": pid }))
        }
        Err(e) => {
            tracing::error!(
                agent_id = req.agent_id,
                error = %e,
                "Spawn failed"
            );
            Json(serde_json::json!({ "ok": false, "error": e.to_string() }))
        }
    }
}

async fn handle_status(State(state): State<Arc<Mutex<AppState>>>) -> Json<StatusResponse> {
    let state = state.lock().await;

    let agents = state
        .spawner
        .list_agents()
        .into_iter()
        .map(|(agent_id, sprint_id, pid)| {
            let alive = spawner::is_process_alive(pid);
            let last_heartbeat = state
                .heartbeats
                .last_heartbeat(&agent_id)
                .map(|t| t.to_rfc3339());

            AgentInfo {
                agent_id,
                sprint_id,
                pid,
                alive,
                last_heartbeat,
            }
        })
        .collect();

    Json(StatusResponse { agents })
}

async fn handle_health() -> &'static str {
    "ok"
}
