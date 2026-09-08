(() => {
  const invoke = (cmd, args) => window.__TAURI__.core.invoke(cmd, args);
  const providers = ["claude", "cursor", "codex"];

  async function load() {
    const prefs = await invoke("get_preferences");
    for (const id of providers) {
      const el = document.querySelector(`[data-provider="${id}"]`);
      el.checked = !(prefs.disconnectedProviders || []).includes(id);
    }
    document.getElementById("edge").value = prefs.notchEdge || "right";
    document.getElementById("visibility").value = prefs.notchVisibility || "onHover";
    document.getElementById("autostart").checked = !!prefs.launchAtLogin;
  }

  async function save() {
    const disconnectedProviders = providers.filter(
      (id) => !document.querySelector(`[data-provider="${id}"]`).checked
    );
    const prefs = {
      disconnectedProviders,
      notchEdge: document.getElementById("edge").value,
      notchVisibility: document.getElementById("visibility").value,
      launchAtLogin: document.getElementById("autostart").checked,
    };
    await invoke("set_preferences", { prefs });
    await invoke("refresh_all");
    const btn = document.getElementById("save");
    btn.textContent = "Saved";
    setTimeout(() => {
      btn.textContent = "Save";
    }, 1200);
  }

  document.getElementById("save").addEventListener("click", () => {
    save().catch((err) => {
      console.error(err);
      alert(String(err));
    });
  });

  load().catch(console.error);
})();
