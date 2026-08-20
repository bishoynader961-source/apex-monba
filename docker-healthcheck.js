// Frontend container healthcheck (Next.js standalone).
// Runs as a plain `node` script (no inline shell escaping) so Docker's health
// probe cannot be broken by quote handling. Tries the dedicated /api/health
// endpoint first, then falls back to / (the landing page returns 200 once the
// server is up). Exits 0 on any 2xx response, 1 otherwise.
const http = require("http");

const port = process.env.PORT || 3000;
const paths = ["/api/health", "/"];

function probe(index) {
  if (index >= paths.length) process.exit(1);
  const req = http.get(
    { host: "127.0.0.1", port, path: paths[index] },
    (res) => {
      if (res.statusCode >= 200 && res.statusCode < 300) process.exit(0);
      probe(index + 1);
    }
  );
  req.on("error", () => probe(index + 1));
  req.setTimeout(4000, () => {
    req.destroy();
    probe(index + 1);
  });
}

probe(0);
