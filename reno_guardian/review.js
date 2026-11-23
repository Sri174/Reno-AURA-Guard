let token = "";
const status = document.querySelector("#status");
const content = document.querySelector("#content");
async function request(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {Authorization: "Bearer " + token, "Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) throw new Error("Request failed (" + response.status + "). Check access or provider status.");
  return response.json();
}
function element(tag, text, parent) {
  const node = document.createElement(tag);
  node.textContent = text;
  parent.append(node);
  return node;
}
async function load() {
  const [incidents, proposals] = await Promise.all([request("/incidents"), request("/proposals")]);
  content.replaceChildren();
  if (!incidents.length) element("p", "No incidents have been received.", content);
  for (const incident of incidents) {
    const panel = element("article", "", content);
    element("h2", incident.title, panel);
    element("small", incident.severity + " · " + incident.state + " · " + incident.occurrences + " observations", panel);
    element("pre", incident.evidence, panel);
    const investigate = element("button", "Investigate", panel);
    investigate.addEventListener("click", () => run(investigate, async () => {
      await request("/incidents/" + incident.id + "/investigate", {});
      await load();
    }));
    const proposal = proposals.find(p => p.incident === incident.id && p.state !== "superseded");
    if (proposal) {
      element("h3", "Proposed response", panel);
      element("pre", proposal.content, panel);
      element("small", "State " + proposal.state + " · Expires " + new Date(proposal.expires * 1000).toLocaleString(), panel);
      if (proposal.state === "pending" && proposal.expires * 1000 > Date.now() && incident.state === "open") {
        const approve = element("button", "Approve this proposal", panel);
        approve.addEventListener("click", () => run(approve, async () => {
          const result = await request("/proposals/" + proposal.id + "/approve", {digest: proposal.digest});
          await load();
          status.textContent = "Approval recorded. " + result.execution;
        }));
      }
    }
  }
}
async function run(button, action) {
  button.disabled = true;
  status.textContent = "Working…";
  try { await action(); if(status.textContent === "Working…") status.textContent = ""; }
  catch (error) { status.textContent = error.message; }
  finally { button.disabled = false; }
}
document.querySelector("#login").addEventListener("submit", event => {
  event.preventDefault();
  token = document.querySelector("#token").value;
  document.querySelector("#token").value = "";
  run(event.submitter, load);
});
