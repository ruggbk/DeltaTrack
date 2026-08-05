# Release: promoting `develop` to `main`

`develop` is the integration branch and `main` is the protected release branch (see
[CONTRIBUTING.md](../CONTRIBUTING.md#branching)). Promotion is the only way work reaches
either public surface, and it is a deliberate, human-initiated step.

**Promotion is the maintainer's call to initiate.** A runbook step saying "open the
pull request" is a description of the sequence, not standing authorization to run it.
Raise it as a question and let the maintainer decide.

## Two surfaces, both keyed off `main`

Promotion updates both at once. Neither tracks `develop`.

| Surface | What it is | How it updates |
|---|---|---|
| The hosted comparison app | The FastAPI upload app | The server pulls from `main`, then a redeploy (below) |
| The example reports | Static reports linked from the README's "See it in action" | `.github/workflows/update-examples.yml`, on push to `main`. Regenerates the examples and deploys to Pages |

Because the example reports regenerate from `main`, they lag whatever is on `develop`.
A long gap between promotions means the project's front page shows visitors an older
build of the renderer than the one the code produces.

## Sequence

Do these in order. The steps are separable and the ordering is what makes a failure
attributable.

1. **Confirm continuous integration is green on the exact commit being promoted.**
   CI runs on pull requests, on pushes to **both** `main` and `develop`, and on
   `merge_group` events, and the `develop` push run is the same full matrix a pull
   request gets. So the integrated state *is* checked automatically. Two separate
   mechanisms cover it: the merge queue tests each merge commit before it lands
   (prevention), and the push run re-tests it afterwards, attributed to the merge that
   caused any breakage (detection). See the header comment in `.github/workflows/ci.yml`
   for why both are kept. The trigger itself is pinned by
   `tests/test_ci_workflow.py::test_ci_runs_on_pushes_to_develop`, so this statement
   fails loudly rather than silently going stale if the trigger is ever removed.

   Check the run attributed to the head commit being promoted, not merely the branch's
   most recent green run: another pull request can land in between, and a green mark on
   an earlier commit says nothing about the one going to `main`. A local full run is a
   fallback if no run exists for that commit, not the gate.

2. **Check the example-generation workflow can still run.** `update-examples.yml` fetches
   a bill and runs two comparisons. It executes only on `main`, so any change to fetching
   or to the comparison entry points that landed on `develop` has never run in this
   workflow's environment. Exercise those commands against the current `develop` before
   promoting rather than discovering it in a Pages deploy.

3. **Open the promotion pull request** from `develop` to `main`. `main` is protected; the
   maintainer merges.

4. **Redeploy the hosted app.** The server pulls from `main` and restarts. The command is
   in [docs/web-compare.md](web-compare.md); hosting specifics live outside this
   repository.

5. **Smoke both surfaces.** Run a real comparison on the hosted app, and open the
   README's "See it in action" links to confirm they now serve the newly generated
   reports. Checking only one surface leaves the other unverified, and they fail
   independently.

6. **Leave a rollback window.** Rollback is reverting the promotion pull request and
   redeploying. Do not start unrelated work on `main` inside that window.

## What the workflow does not exercise

Step 1 reads a continuous-integration run and step 2 can be run locally. The Pages
publishing steps in `update-examples.yml`
(`configure-pages`, `upload-pages-artifact`, `deploy-pages`) cannot: they need the Pages
environment and only run on `main`. They are unchanged from previous successful runs, so
they are low risk, but a promotion has no local evidence about them. If Pages publishing
fails, that is where to look first.

## Files that look disposable and are not

The committed example reports are the README's front-page demo and a live Pages surface.
They regenerate on promotion, which makes them look like build output that can be deleted
or moved freely. Deleting or relocating them without repointing the README leaves dead
links on the project's front page, and no continuous-integration check catches it.
