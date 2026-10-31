/* Handoff — service worker (Web Push phone alerts, Oct 31 round).
   Receives push messages with the app closed and shows them like
   clinical text messages: the notification names the patient and what
   changed; tapping it opens the exact record.

   URGENT items (payload.urgent — escalations and anything that needs
   acknowledgment) get attention handling the platform allows a web
   app: a distinct vibration pattern (Android), renotify so a repeat
   change re-alerts instead of silently stacking under the same tag,
   and requireInteraction so the alert stays on screen on desktop
   until it is dealt with. The audible tone itself is the phone's own
   notification sound — a web app cannot choose or force it. */
self.addEventListener('install', function (e) { self.skipWaiting(); });
self.addEventListener('activate', function (e) { e.waitUntil(self.clients.claim()); });
/* A fetch handler is required for installability; it is a plain
   network pass-through — the app is always used live. */
self.addEventListener('fetch', function (e) { /* pass-through */ });

self.addEventListener('push', function (e) {
    var d = {};
    try { d = e.data.json(); } catch (err) { d = { title: 'Handoff', body: e.data ? e.data.text() : '' }; }
    var urgent = !!d.urgent;
    var opts = {
        body: d.body || '',
        icon: '/static/img/icon-192.png',
        badge: '/static/img/icon-192.png',
        tag: d.tag || undefined,
        data: { url: d.url || '/' },
        renotify: urgent,
        requireInteraction: urgent
    };
    if (urgent) {
        /* Attention pattern: buzz-pause-buzz-pause-long buzz. */
        opts.vibrate = [200, 100, 200, 100, 450];
    } else {
        opts.vibrate = [120];
    }
    e.waitUntil(self.registration.showNotification(d.title || 'Handoff', opts));
});

self.addEventListener('notificationclick', function (e) {
    e.notification.close();
    var target = (e.notification.data && e.notification.data.url) || '/';
    e.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (wins) {
            for (var i = 0; i < wins.length; i++) {
                if ('focus' in wins[i]) {
                    wins[i].navigate(target);
                    return wins[i].focus();
                }
            }
            return self.clients.openWindow(target);
        })
    );
});
