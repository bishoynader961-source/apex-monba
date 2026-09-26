// ── Recovery window logic (Step 2.3) ─────────────────────────────────────────
// SECURITY RULES:
//   * Talks ONLY to the three whitelisted Tauri commands exposed by
//     fix_engine.rs. No fetch(), no network, no evaluation of fix content.
//   * Renders only fixed strings from this file plus the JSON returned by
//     recovery_get_diagnostics (which contains version/OS/crash-filename).
//   * The admin key field is type=password and its value only ever goes to
//     the recovery_apply_fix IPC call — never logged, never displayed.
(function () {
  "use strict";

  // Tauri v2 global IPC bridge (withGlobalTauri is enabled for this window
  // via the recovery capability; the main window keeps its own config).
  var invoke = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
  var openUrl = window.__TAURI__ && window.__TAURI__.shell && window.__TAURI__.shell.open;

  var SUPPORT_EMAIL = "pharmacypro.support@gmail.com";

  function $(id) {
    return document.getElementById(id);
  }

  function setDone(el, msg) {
    el.textContent = msg;
    setTimeout(function () {
      el.textContent = "";
    }, 4000);
  }

  // ── Step 1: diagnostics ──────────────────────────────────────────────────
  var diagText = "Diagnostics unavailable.";
  if (invoke) {
    invoke("recovery_get_diagnostics")
      .then(function (json) {
        try {
          var d = JSON.parse(json);
          diagText =
            "App version: " + d.appVersion + "\n" +
            "OS: " + d.os + "\n" +
            "Latest crash file: " + d.lastCrashFile;
        } catch (e) {
          diagText = json;
        }
        $("diag").textContent = diagText;
      })
      .catch(function () {
        $("diag").textContent = "Diagnostics unavailable.";
      });
  } else {
    $("diag").textContent = "IPC bridge unavailable.";
  }

  $("btn-copy").addEventListener("click", function () {
    var done = function (ok) {
      setDone($("copy-result"), ok ? "\u2713 Copied" : "Copy failed \u2014 select the text above manually");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(diagText).then(
        function () { done(true); },
        function () { done(false); }
      );
    } else {
      // Clipboard API blocked: fall back to a selection-based copy.
      var range = document.createRange();
      range.selectNodeContents($("diag"));
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      done(document.execCommand && document.execCommand("copy"));
    }
  });

  // ── Step 2: email support ────────────────────────────────────────────────
  // mailto: only — the user's own email client, user sees everything first
  // (invariant #6). Body carries the sanitized diagnostic block only.
  function buildMailto() {
    var subject = "Pharmacy Suite support request (v" + (diagText.match(/App version: (.*)/) || ["", "?"])[1] + ")";
    var body =
      "Describe the problem:\n\n\n" +
      "--- Diagnostic info (no patient data) ---\n" + diagText + "\n";
    return (
      "mailto:" + SUPPORT_EMAIL +
      "?subject=" + encodeURIComponent(subject) +
      "&body=" + encodeURIComponent(body)
    );
  }

  $("btn-email").addEventListener("click", function () {
    var url = buildMailto();
    if (openUrl) {
      openUrl(url).catch(function () {
        window.location.href = url;
      });
    } else {
      window.location.href = url;
    }
  });

  $("btn-copy-email").addEventListener("click", function () {
    var done = function (ok) {
      setDone($("email-result"), ok ? "\u2713 Copied" : "Copy failed");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(SUPPORT_EMAIL).then(
        function () { done(true); },
        function () { done(false); }
      );
    } else {
      done(false);
    }
  });

  // ── Step 3: apply fix code ───────────────────────────────────────────────
  $("btn-fix").addEventListener("click", function () {
    var result = $("fix-result");
    var adminKey = $("fix-admin-key").value;
    var fixCode = $("fix-code").value;
    result.className = "";
    result.textContent = "";

    if (!adminKey || !fixCode.trim()) {
      result.className = "err";
      result.textContent = "Enter both the admin key and the fix code.";
      return;
    }
    if (!invoke) {
      result.className = "err";
      result.textContent = "FIX_ENGINE_UNAVAILABLE";
      return;
    }
    $("btn-fix").disabled = true;
    invoke("recovery_apply_fix", { adminKey: adminKey, fixCode: fixCode })
      .then(function (message) {
        result.className = "ok";
        result.textContent = "\u2713 " + message;
      })
      .catch(function (err) {
        // err is one of the fixed friendly codes from fix_engine.rs
        result.className = "err";
        result.textContent = String(err);
      })
      .then(function () {
        $("btn-fix").disabled = false;
      });
  });

  // ── Step 4: emergency reset (two-step confirm) ───────────────────────────
  $("btn-reset").addEventListener("click", function () {
    $("btn-reset").classList.add("hidden");
    $("reset-confirm").classList.remove("hidden");
  });
  $("btn-reset-no").addEventListener("click", function () {
    $("reset-confirm").classList.add("hidden");
    $("btn-reset").classList.remove("hidden");
  });
  $("btn-reset-yes").addEventListener("click", function () {
    var result = $("reset-result");
    var adminKey = $("fix-admin-key").value;
    result.className = "";
    result.textContent = "";
    if (!adminKey) {
      result.className = "err";
      result.textContent = "Enter the admin key from support first.";
      return;
    }
    if (!invoke) {
      result.className = "err";
      result.textContent = "FIX_ENGINE_UNAVAILABLE";
      return;
    }
    invoke("recovery_reset_config", { adminKey: adminKey })
      .then(function (message) {
        result.className = "ok";
        result.textContent = "\u2713 " + message;
      })
      .catch(function (err) {
        result.className = "err";
        result.textContent = String(err);
      })
      .then(function () {
        $("reset-confirm").classList.add("hidden");
        $("btn-reset").classList.remove("hidden");
      });
  });

  // ── Step 5: close ────────────────────────────────────────────────────────
  $("btn-exit").addEventListener("click", function () {
    window.close();
  });
})();
