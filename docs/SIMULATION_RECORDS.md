# Simulation records

Code: `backend/app/storage/` (`records.py` for storage, `assessment.py` to
build a record), `backend/app/core/model_registry.py` (methods and
versions). UI: the **Simulation records** page.

A record is a saved assessment of one session at one moment. It stores what
was configured, what the models calculated, how each value was obtained, and
how far it can be trusted. **Records are immutable.** A new assessment is a
new record; there is no update.

## Contents of a record

| Section | Contents |
|---|---|
| `header` | Scenario id and name, data classification, session id, simulated time, model mode, fluid model, run status, app version |
| `inputs` | Boundary conditions; black-oil or single-phase fluid; every valve and choke (position, command, state); chemical injection; hydraulic supplies; the full sand and choke input set (geomechanics, completion, sand, measured history, detector, trim, cavitation, API RP 14E, acceptance, thresholds, operating history, inspections) |
| `results` | Every transmitter reading; phase rates at the sandface and the manifold; mass balance; MPFM measured, true and difference with uncertainty; sand rates; SDT-101; measured-history summary; velocities; wear by criterion with remaining-life ranges; health, recommendation and confidence; Cv tracking; cavitation; erosional velocity |
| `provenance` | How each input group and result was obtained (below) |
| `methods` | Model-registry entry for every module used: method, version, model status, validation statement, document |
| `assumptions` | Multiphase and erosion limitations, and every ASSUMED value |
| `uncertainty` | MPFM uncertainty, erosion uncertainty components, P10/P50/P90 remaining life, detector uncertainty, bubble-point sensitivity |
| `validation` | Overall status, range of model statuses, erosion confidence, data classification and a plain statement |

## Provenance classes

| Class | Meaning | Example |
|---|---|---|
| measured | entered or imported field measurement | sand rate from the latest measured record |
| imported | brought in from a file | measured sand history from CSV (`source = csv_import`) |
| estimated | calculated by a correlation or screening model | predicted sand rate, wear, cavitation |
| simulated | calculated by the simulation | transmitter readings, phase rates, valve states, the MPFM reading |
| configured | entered by the operator or set by the scenario | boundary conditions, site sand and choke data |
| illustrative | demonstration data, not field data | the example input set; "partly edited" once changed |

The engine records where the sand and choke inputs came from
(`sand_inputs_origin`):

- the scenario preset;
- the illustrative example;
- the illustrative example, edited;
- entered by the user.

Edited example data stay labelled illustrative until every value has been
replaced with site data.

## Model status and validation

Each module's status is on the specification's ladder:

1. analytical estimate;
2. correlation-based screening;
3. simplified simulation;
4. surrogate-model prediction;
5. high-fidelity CFD;
6. experimentally validated;
7. field-calibrated.

The overall validation of a record reads **"Verified models, not
field-validated"**. The exception is when inspection records have calibrated
the erosion model; then it reads "Field-calibrated erosion". No record claims
a validation the data do not support.

**Versions.** Bump a module's `version` in `model_registry.py` whenever its
equations or constants change. `APP_VERSION` is stamped on every record.

## Storage

- SQLite through the Python standard library; there is no extra service.
- The file is `$SUBSEASIM_DB_PATH`. The default is
  `backend/data/records.sqlite`, which git ignores.
- In Docker the file is `/app/data/records.sqlite`. `/app/data` is a volume
  in `docker-compose.yml`.
- **On Railway, add a volume mounted at `/app/data`.** Without it, records
  are lost at every redeploy.
- Table `simulation_records` holds the summary columns used for listing,
  plus the full record as JSON in `body`.
- Table `meta` holds `schema_version` (2: `has_comparison`; version-1 files are migrated in place).

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions/{sid}/records` | Save the current assessment `{label, notes?}` (201, summary) |
| GET | `/api/records?scenario_id=&limit=` | List summaries, newest first |
| GET | `/api/records/{id}` | Full record |
| GET | `/api/records/{id}/export` | Download as JSON |
| DELETE | `/api/records/{id}` | Delete (204) |

## Verification

`backend/tests/test_records.py` checks:

- every registry entry is complete and on the status ladder;
- a record reproduces the live snapshot (valve positions, transmitter
  values, health);
- provenance for illustrative, edited, imported and simulated data;
- the save, list, get and delete round trip, including the schema version;
- the API, including export and validation of the label.

`frontend/src/records.test.tsx` and the end-to-end test cover the page.
