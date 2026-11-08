// MotionX <-> Streamlit bridge: passes Python's arguments to the page and sends the page's actions back (no build step).
(function () {
  function send(type, data) { window.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data || {}), "*"); }
  window.addEventListener("message", function (e) {
    var d = e.data; if (!d || d.type !== "streamlit:render") return;
    if (window.onStreamlitArgs) window.onStreamlitArgs(d.args || {});
  });
  window.streamlitSend = function (v) { send("streamlit:setComponentValue", { value: v, dataType: "json" }); };
  window.streamlitHeight = function (h) { if (h !== window.__h) { window.__h = h; send("streamlit:setFrameHeight", { height: h }); } };
  send("streamlit:componentReady", { apiVersion: 1 });
  window.streamlitHeight(860);
})();
