mod model;
mod prefs;
mod providers;
mod store;

use prefs::{NotchEdge, Preferences};
use store::UsageStore;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, State, WebviewUrl,
    WebviewWindowBuilder,
};

#[tauri::command]
async fn get_snapshots(store: State<'_, UsageStore>) -> Result<Vec<serde_json::Value>, String> {
    Ok(store.snapshots().await)
}

#[tauri::command]
async fn get_preferences(store: State<'_, UsageStore>) -> Result<Preferences, String> {
    Ok(store.prefs().await)
}

#[tauri::command]
async fn set_preferences(
    app: AppHandle,
    store: State<'_, UsageStore>,
    mut prefs: Preferences,
) -> Result<(), String> {
    prefs.set_autostart(prefs.launch_at_login)?;
    store.set_prefs(prefs.clone()).await?;
    position_overlay(&app, &prefs.notch_edge)?;
    let _ = app.emit("preferences-changed", &prefs);
    Ok(())
}

#[tauri::command]
async fn refresh_provider(store: State<'_, UsageStore>, id: String) -> Result<(), String> {
    store.refresh_one(&id).await;
    Ok(())
}

#[tauri::command]
async fn refresh_all(store: State<'_, UsageStore>) -> Result<Vec<serde_json::Value>, String> {
    store.refresh_all().await;
    Ok(store.snapshots().await)
}

#[tauri::command]
fn open_settings(app: AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("settings") {
        let _ = win.show();
        let _ = win.set_focus();
        return Ok(());
    }
    WebviewWindowBuilder::new(&app, "settings", WebviewUrl::App("settings.html".into()))
        .title("Codenotch Settings")
        .inner_size(420.0, 560.0)
        .resizable(false)
        .decorations(true)
        .center()
        .build()
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn position_overlay(app: &AppHandle, edge: &NotchEdge) -> Result<(), String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "main window missing".to_string())?;
    let monitor = window
        .current_monitor()
        .map_err(|e| e.to_string())?
        .or_else(|| window.primary_monitor().ok().flatten())
        .ok_or_else(|| "no monitor".to_string())?;

    let size = monitor.size();
    let pos = monitor.position();
    let scale = monitor.scale_factor();

    // Overlay panel large enough for expanded notch + tooltip.
    let (w, h) = match edge {
        NotchEdge::Left | NotchEdge::Right => (420u32, 720u32),
        NotchEdge::Top | NotchEdge::Bottom => (900u32, 360u32),
    };
    let _ = window.set_size(tauri::Size::Physical(PhysicalSize::new(w, h)));

    let x = match edge {
        NotchEdge::Right => pos.x + size.width as i32 - w as i32,
        NotchEdge::Left => pos.x,
        NotchEdge::Top | NotchEdge::Bottom => {
            pos.x + ((size.width as i32 - w as i32) / 2)
        }
    };
    let y = match edge {
        NotchEdge::Right | NotchEdge::Left => {
            pos.y + ((size.height as i32 - h as i32) / 2)
        }
        NotchEdge::Top => pos.y,
        NotchEdge::Bottom => pos.y + size.height as i32 - h as i32,
    };

    let _ = window.set_position(tauri::Position::Physical(PhysicalPosition::new(x, y)));
    let _ = scale; // reserved for future CSS pixel alignment
    Ok(())
}

fn setup_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let settings = MenuItem::with_id(app, "settings", "Settings…", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Codenotch", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&settings, &quit])?;

    let _tray = TrayIconBuilder::new()
        .menu(&menu)
        .tooltip("Codenotch")
        .on_menu_event(|app, event| match event.id.as_ref() {
            "settings" => {
                let _ = open_settings(app.clone());
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                let _ = open_settings(app.clone());
            }
        })
        .build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "codenotch=info".into()),
        )
        .init();

    let demo = std::env::var("CODENOTCH_DEMO").ok().as_deref() == Some("1");
    let prefs = Preferences::load();
    let store = UsageStore::new(prefs.clone(), demo);

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(store.clone())
        .invoke_handler(tauri::generate_handler![
            get_snapshots,
            get_preferences,
            set_preferences,
            refresh_provider,
            refresh_all,
            open_settings
        ])
        .setup(move |app| {
            let edge = prefs.notch_edge.clone();
            position_overlay(app.handle(), &edge)?;
            setup_tray(app.handle())?;

            let handle = app.handle().clone();
            let poll_store = store.clone();
            tauri::async_runtime::spawn(async move {
                poll_store.refresh_all().await;
                let _ = handle.emit("snapshots-updated", poll_store.snapshots().await);
                loop {
                    tokio::time::sleep(std::time::Duration::from_secs(60)).await;
                    poll_store.refresh_all().await;
                    let _ = handle.emit("snapshots-updated", poll_store.snapshots().await);
                }
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Codenotch");
}
