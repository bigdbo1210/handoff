/* Handoff — phone alerts (Web Push) enable/disable control.
   Renders into any element with id="push-alerts-box" (the notification
   bell panel and the Notifications Center). Zero-cost channel: the
   browser's own push service delivers; there is no SMS and no paid
   relay. iPhone rule (Apple): push works only for the site saved to
   the Home Screen (iOS 16.4+) — when we detect that case we show the
   one-line instruction instead of a button that cannot work. */
(function () {
    var box = document.getElementById('push-alerts-box');
    if (!box) return;

    function say(html) { box.innerHTML = html; }
    function isIOS() {
        return /iphone|ipad|ipod/i.test(navigator.userAgent) ||
            (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    }
    function isStandalone() {
        return window.navigator.standalone === true ||
            (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches);
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        if (isIOS() && !isStandalone()) {
            say('<span class="push-note">📱 <strong>Phone alerts on iPhone:</strong> tap the Share button, then <strong>Add to Home Screen</strong>. Open Handoff from the new home-screen icon and turn alerts on there.</span>');
        } else {
            say('<span class="push-note">Phone alerts are not supported in this browser.</span>');
        }
        return;
    }

    function urlB64ToUint8Array(b64) {
        var pad = '='.repeat((4 - (b64.length % 4)) % 4);
        var raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
        var arr = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
        return arr;
    }

    async function currentSub() {
        var reg = await navigator.serviceWorker.register('/sw.js');
        return { reg: reg, sub: await reg.pushManager.getSubscription() };
    }

    function render(sub) {
        if (sub) {
            say('<button type="button" class="push-btn push-on" id="push-toggle">📱 Phone alerts: ON for this device — tap to turn off</button>');
        } else {
            say('<button type="button" class="push-btn" id="push-toggle">📱 Enable phone alerts</button>' +
                '<span class="push-note">Alerts like a clinical text: patient + what changed, tap to open the record. Works with the app closed.</span>');
        }
        var btn = document.getElementById('push-toggle');
        if (btn) btn.addEventListener('click', sub ? disable : enable);
    }

    async function enable() {
        try {
            var r = await fetch('/api/push/key');
            if (!r.ok) throw new Error('key');
            var key = (await r.json()).publicKey;
            var perm = await Notification.requestPermission();
            if (perm !== 'granted') {
                say('<span class="push-note">Phone alerts need notification permission — allow notifications for this site in your browser settings, then tap Enable again.</span>');
                return;
            }
            var s = await currentSub();
            var sub = s.sub || await s.reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlB64ToUint8Array(key)
            });
            var resp = await fetch('/push/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(sub)
            });
            if (!resp.ok) throw new Error('save');
            render(sub);
        } catch (e) {
            say('<span class="push-note">Could not turn on phone alerts on this device — the Notifications Center still shows everything.</span>');
        }
    }

    async function disable() {
        try {
            var s = await currentSub();
            if (s.sub) {
                await fetch('/push/unsubscribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ endpoint: s.sub.endpoint })
                });
                await s.sub.unsubscribe();
            }
        } catch (e) { /* turning off must never trap the user */ }
        render(null);
    }

    currentSub().then(function (s) { render(s.sub); }).catch(function () {
        say('<span class="push-note">Phone alerts are unavailable right now.</span>');
    });
})();
