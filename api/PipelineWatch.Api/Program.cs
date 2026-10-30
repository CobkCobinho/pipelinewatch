using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);
if (builder.Configuration["urls"] is null)
    builder.WebHost.UseUrls("http://127.0.0.1:5088");
var app = builder.Build();
var codeRoot = FindRoot();
var root = builder.Configuration["PipelineWatch:Root"] ?? codeRoot;
var snapshotPath = Path.Combine(root, "data", "gold", "snapshot.json");
var gate = new SemaphoreSlim(1, 1);
var tables = new HashSet<string> { "runs", "events", "errors", "daily", "components" };

app.MapGet("/", () => Results.Ok(new {
    name = "PipelineWatch", synthetic = true, health = "/health",
    summary = "/api/summary", runs = "/api/runs", graph = "/api/graph",
    powerbi = "/api/powerbi/runs", note = "Dados e durações simulados. Uso local de demonstração."
}));
app.MapGet("/health", () => Results.Ok(new { status = File.Exists(snapshotPath) ? "ready" : "awaiting_data", synthetic = true }));

app.MapGet("/api/summary", async () => {
    var snapshot = await ReadSnapshot();
    var runs = snapshot.GetProperty("runs").EnumerateArray().ToArray();
    long received = runs.Sum(r => r.GetProperty("input_rows").GetInt64());
    long accepted = runs.Sum(r => r.GetProperty("accepted_rows").GetInt64());
    return Results.Ok(new {
        synthetic = true, executions = runs.Length,
        failures = runs.Count(r => r.GetProperty("status").GetString() == "Falha"),
        inputRows = received, acceptedRows = accepted, rejectedRows = received - accepted,
        qualityPercent = received == 0 ? (double?)null : Math.Round(100.0 * accepted / received, 2),
        generatedAt = snapshot.GetProperty("metadata").GetProperty("generated_at").GetString(),
        durationNote = snapshot.GetProperty("metadata").GetProperty("duration_note").GetString()
    });
});

app.MapGet("/api/runs", async (int? limit, string? status) => {
    if (limit is < 1 or > 1000) return Results.BadRequest(new { error = "limit deve estar entre 1 e 1000" });
    if (status is not null && status is not ("Sucesso" or "Alerta" or "Falha"))
        return Results.BadRequest(new { error = "status inválido" });
    var snapshot = await ReadSnapshot();
    var runs = snapshot.GetProperty("runs").EnumerateArray().Where(r =>
        status is null || r.GetProperty("status").GetString() == status)
        .OrderByDescending(r => r.GetProperty("created_at").GetString()).Take(limit ?? 100);
    return Results.Ok(runs.ToArray());
});

app.MapGet("/api/runs/{runId:guid}", async (Guid runId) => {
    var snapshot = await ReadSnapshot();
    var run = snapshot.GetProperty("runs").EnumerateArray()
        .FirstOrDefault(r => r.GetProperty("run_id").GetString() == runId.ToString());
    if (run.ValueKind == JsonValueKind.Undefined) return Results.NotFound();
    return Results.Ok(new {
        run,
        events = snapshot.GetProperty("events").EnumerateArray().Where(Matches).ToArray(),
        errors = snapshot.GetProperty("errors").EnumerateArray().Where(Matches).ToArray()
    });
    bool Matches(JsonElement r) => r.GetProperty("run_id").GetString() == runId.ToString();
});

app.MapGet("/api/graph", async (Guid? runId) => {
    var snapshot = await ReadSnapshot();
    if (runId.HasValue && !snapshot.GetProperty("runs").EnumerateArray().Any(r =>
        r.GetProperty("run_id").GetString() == runId.Value.ToString())) return Results.NotFound();
    var events = snapshot.GetProperty("events").EnumerateArray().Where(r =>
        !runId.HasValue || r.GetProperty("run_id").GetString() == runId.Value.ToString()).ToArray();
    var nodes = events.GroupBy(r => r.GetProperty("stage_name").GetString())
        .Select(g => new {
            id = g.Key,
            inputRows = g.Sum(r => r.GetProperty("input_rows").GetInt64()),
            outputRows = g.Sum(r => r.GetProperty("output_rows").GetInt64()),
            failures = g.Count(r => r.GetProperty("status").GetString() == "Falha"),
            alerts = g.Count(r => r.GetProperty("status").GetString() == "Alerta"),
            simulatedDurationMs = g.Sum(r => r.GetProperty("duration_ms").GetDouble())
        });
    return Results.Ok(new { synthetic = true, nodes = nodes.ToArray(),
        edges = snapshot.GetProperty("metadata").GetProperty("edges") });
});

app.MapGet("/api/components", async () => (await ReadSnapshot()).GetProperty("components"));

app.MapGet("/api/powerbi/{table}", async (string table) => {
    if (!tables.Contains(table)) return Results.NotFound();
    var snapshot = await ReadSnapshot();
    var rows = snapshot.GetProperty(table).EnumerateArray().ToArray();
    // Os CSVs exportados pelo Python preservam os cabeçalhos mesmo com zero linhas.
    if (rows.Length == 0)
        return Results.Text(await File.ReadAllTextAsync(Path.Combine(root, "data", "gold", table + ".csv")), "text/csv; charset=utf-8");
    var headers = rows[0].EnumerateObject().Select(p => p.Name).ToArray();
    var csv = new StringBuilder().AppendLine(string.Join(',', headers.Select(Escape)));
    foreach (var row in rows)
        csv.AppendLine(string.Join(',', headers.Select(h => Escape(row.GetProperty(h).ToString()))));
    return Results.Text(csv.ToString(), "text/csv; charset=utf-8");
});

app.MapPost("/api/runs", async (RunRequest request, CancellationToken cancellation) => {
    if (request.Count is < 1 or > 10_000 || request.Component is < 0 or > 7 ||
        request.Scenario is not ("normal" or "high_rejection" or "source_failure"))
        return Results.BadRequest(new { error = "count: 1..10000; component: 0..7; scenario: normal, high_rejection ou source_failure" });
    if (!await gate.WaitAsync(0, cancellation))
        return Results.Conflict(new { error = "Uma execução já está em andamento." });
    try {
        var start = new ProcessStartInfo {
            FileName = builder.Configuration["Python:Executable"] ?? "python",
            WorkingDirectory = codeRoot, UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true
        };
        foreach (var argument in new[] { "-m", "pipelinewatch", "run", "--root", root,
            "--seed", request.Seed.ToString(CultureInfo.InvariantCulture),
            "--count", request.Count.ToString(CultureInfo.InvariantCulture),
            "--component", request.Component.ToString(CultureInfo.InvariantCulture), "--scenario", request.Scenario })
            start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Não foi possível iniciar o Python.");
        var stdout = process.StandardOutput.ReadToEndAsync(cancellation);
        var stderr = process.StandardError.ReadToEndAsync(cancellation);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellation);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException) {
            if (!process.HasExited) process.Kill(entireProcessTree: true);
            return Results.Problem("Execução cancelada ou tempo limite excedido.", statusCode: 408);
        }
        var output = await stdout;
        var error = await stderr;
        if (process.ExitCode != 0) {
            app.Logger.LogError("Pipeline Python falhou: {Error}", error);
            return Results.Problem("O pipeline não terminou. Consulte o log local.");
        }
        using var result = JsonDocument.Parse(output);
        var id = result.RootElement.GetProperty("run_id").GetString();
        return Results.Created($"/api/runs/{id}", result.RootElement.Clone());
    }
    catch (Exception e) when (e is System.ComponentModel.Win32Exception or InvalidOperationException) {
        app.Logger.LogError(e, "Falha ao iniciar o pipeline");
        return Results.Problem("Python indisponível. Configure Python__Executable ou o PATH.");
    }
    finally { gate.Release(); }
});

app.UseExceptionHandler(handler => handler.Run(async context => {
    context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
    await context.Response.WriteAsJsonAsync(new {
        error = "Snapshot indisponível. Execute python -m pipelinewatch demo na raiz do projeto.", synthetic = true
    });
}));

app.Run();

async Task<JsonElement> ReadSnapshot() {
    using var document = JsonDocument.Parse(await File.ReadAllTextAsync(snapshotPath));
    return document.RootElement.Clone();
}
static string Escape(string text) => text.IndexOfAny([',', '"', '\r', '\n']) >= 0
    ? '"' + text.Replace("\"", "\"\"") + '"' : text;
static string FindRoot() {
    for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
        if (File.Exists(Path.Combine(directory.FullName, "sql", "schema.sql"))) return directory.FullName;
    throw new DirectoryNotFoundException("Defina PipelineWatch__Root para a raiz do projeto.");
}
record RunRequest(int Seed = 2026, int Count = 200, int Component = 0, string Scenario = "normal");
