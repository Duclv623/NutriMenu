"use strict";
(async () => {
  const response = await fetch("/openapi.json");
  if (!response.ok) throw new Error("Không đọc được OpenAPI");
  const schema = await response.json();
  for (const [path, methods] of Object.entries(schema.paths)) {
    for (const [method, spec] of Object.entries(methods)) {
      const detail = document.createElement("details");
      const title = document.createElement("summary");
      title.textContent = `${method.toUpperCase()} ${path} — ${spec.summary || ""}`;
      const body = document.createElement("blockquote"); body.textContent = JSON.stringify(spec, null, 2);
      detail.append(title, body); document.getElementById("endpoints").append(detail);
    }
  }
  for (const [name, spec] of Object.entries(schema.components.schemas)) {
    const detail = document.createElement("details"); const title = document.createElement("summary"); title.textContent = name;
    const body = document.createElement("blockquote"); body.textContent = JSON.stringify(spec, null, 2);
    detail.append(title, body); document.getElementById("schemas").append(detail);
  }
})().catch((error) => { document.getElementById("endpoints").textContent = error.message; });
