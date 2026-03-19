// FileSense — Tauri main entry point
//
// Responsibilities:
//   1. Launch the Python sidecar on startup
//   2. Register the global hotkey (Cmd+Shift+Space) to toggle the search window
//   3. Handle window focus/blur behavior (hide on blur, like Spotlight)
//   4. Provide IPC commands for the Svelte frontend

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    AppHandle, Emitter, Manager, RunEvent, WindowEvent,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};
use tauri_plugin_shell::ShellExt;
use std::sync::atomic::{AtomicBool, Ordering};

static SIDECAR_RUNNING: AtomicBool = AtomicBool::new(false);

/// Toggle the main search window visibility
fn toggle_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
        } else {
            let _ = window.show();
            let _ = window.set_focus();
            // Tell the frontend to focus the search input
            let _ = window.emit("focus-search", ());
        }
    }
}

/// Start the Python sidecar process
fn spawn_sidecar(app: &AppHandle) {
    let shell = app.shell();

    println!("[sidecar] Attempting to spawn filesense-python...");

    let sidecar = match shell.sidecar("filesense-python") {
        Ok(s) => {
            println!("[sidecar] Sidecar command created successfully");
            s
        }
        Err(e) => {
            println!("[sidecar] Failed to create sidecar command: {}", e);
            return;
        }
    };

    match sidecar.spawn() {
        Ok((mut _rx, _child)) => {
            println!("[sidecar] Spawned successfully!");
            SIDECAR_RUNNING.store(true, Ordering::SeqCst);

            tauri::async_runtime::spawn(async move {
                use tauri_plugin_shell::process::CommandEvent;
                while let Some(event) = _rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[sidecar:stdout] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            println!("[sidecar:stderr] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Terminated(payload) => {
                            println!("[sidecar] terminated: {:?}", payload);
                            SIDECAR_RUNNING.store(false, Ordering::SeqCst);
                            break;
                        }
                        _ => {}
                    }
                }
            });
        }
        Err(e) => {
            println!("[sidecar] Failed to spawn: {}", e);
        }
    }
}

/// IPC command: get sidecar health status
#[tauri::command]
async fn check_sidecar_health() -> Result<String, String> {
    let client = reqwest::Client::new();
    match client
        .get("http://127.0.0.1:9274/api/health")
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => Ok("healthy".to_string()),
        Ok(resp) => Err(format!("Sidecar returned status {}", resp.status())),
        Err(e) => Err(format!("Sidecar unreachable: {}", e)),
    }
}

/// IPC command: open a file in the default application
#[tauri::command]
async fn open_file(path: String) -> Result<(), String> {
    open::that(&path).map_err(|e| format!("Failed to open {}: {}", path, e))
}

/// IPC command: reveal a file in Finder
#[tauri::command]
async fn reveal_in_finder(path: String) -> Result<(), String> {
    std::process::Command::new("open")
        .args(["-R", &path])
        .spawn()
        .map_err(|e| format!("Failed to reveal {}: {}", path, e))?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state() != ShortcutState::Pressed {
                        return;
                    }
                    let target = Shortcut::new(
                        Some(Modifiers::META | Modifiers::SHIFT),
                        Code::Space,
                    );
                    if shortcut == &target {
                        toggle_window(app);
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            check_sidecar_health,
            open_file,
            reveal_in_finder,
        ])
        .setup(|app| {
            // Register global shortcut
            let shortcut = Shortcut::new(
                Some(Modifiers::META | Modifiers::SHIFT),
                Code::Space,
            );
            app.global_shortcut().register(shortcut)?;

            // Spawn Python sidecar
            spawn_sidecar(app.handle());

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Error building FileSense")
        .run(|app, event| {
            match event {
                RunEvent::ExitRequested { .. } => {
                    SIDECAR_RUNNING.store(false, Ordering::SeqCst);
                }
                RunEvent::Reopen { .. } => {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                _ => {}
            }
        });
}
