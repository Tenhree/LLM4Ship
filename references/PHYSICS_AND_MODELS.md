# Physical conventions and trained models

## Contents

- [Coordinates and displacement](#coordinates-and-displacement)
- [Length and speed scaling](#length-and-speed-scaling)
- [Generator contract](#generator-contract)
- [Predictor contract](#predictor-contract)
- [TD3 contract](#td3-contract)
- [Result interpretation](#result-interpretation)
- [Sources](#sources)

## Coordinates and displacement

Use a half hull with X directed from bow toward stern, Y from the centre plane toward half beam, and Z from bottom toward deck. Interpret the user's beam `B` as the full breadth. Generated CSV coordinates remain at the requested physical scale. Mirror Y only when constructing or displaying the full hull.

Convert displacement mass in metric tonnes to full-hull submerged volume using:

\[
\nabla_s = \frac{1000M_t}{\rho}.
\]

Use the explicit default `rho=1025 kg/m³` if the user does not supply density. Record this assumption. If displacement volume is given directly, preserve it.

Distinguish two dimensionless quantities:

\[
C_B=\frac{\nabla}{LBT},\qquad
q=\frac{\nabla}{LBD}=C_B\frac{T}{D}.
\]

The user's conventional block coefficient is `C_B`. The supplied generator and RL code call their raw-grid volume-conditioning field `CB`. Its semantics follow the original normalized-grid integral, not the conventional block coefficient. Keep that trained field's meaning intact.

The original generator's raw grid is subsequently normalized by its realized coordinate extrema. This can change the physical displacement implied by a nominal conditioning value. The integrated pipeline therefore checks the estimated submerged volume of the final dimensioned point cloud. It calibrates the original scalar conditioning value for each initial latent candidate, with up to 12 generator evaluations per calibration. During a TD3 episode, that calibrated value stays fixed. Calibration addresses output normalization; it does not change the trained weights or redefine the TD3 observation components.

Treat the reported volume as a discrete geometric estimate at the requested draft. The application integrates piecewise-linear full-hull waterline areas from the bottom up to that draft. Report its relative error and tolerance; the default physical tolerance is 5%. Do not call a generated hull displacement-compliant based only on the generator's raw conditioning error. TD3 candidates additionally retain the original raw-volume feasibility check.

## Length and speed scaling

The supplied resistance predictor is a **3 m model-scale** model. Define the conventional full-scale-to-model length ratio:

\[
\lambda=\frac{L_s}{L_m}=\frac{L_s}{3}.
\]

For a consistently based full-scale cloud, apply the same multiplier to all axes:

\[
\mathbf p_m=\frac{\mathbf p_s}{\lambda}.
\]

Beam, depth and draft also divide by `lambda`. Displacement volume divides by `lambda³`. `T/D` is unchanged. Never normalize X, Y and Z independently when converting an existing hull to model scale.

Maintaining `Fr=V/sqrt(gL)` gives:

\[
V_m=\frac{V_s}{\sqrt{\lambda}}.
\]

First convert the full-scale speed to m/s:

- `km/h`: divide by `3.6`.
- `kn`: multiply by `1852/3600`.

For a 90 m ship, `lambda=30`; the model dimensions for `B=15.6 m`, `D=7.5 m` are `B_m=0.52 m`, `D_m=0.25 m`. A 12 kn full-scale speed corresponds to approximately `1.1270913 m/s` at this model scale; 18 kn corresponds to approximately `1.6906369 m/s`. These are analytical conversions, not model predictions.

The output of the predictor remains total resistance in N at the 3 m model scale. A Froude speed conversion does not convert total resistance into a full-scale resistance estimate. This release does not infer full-scale effective power from that total-resistance value.

## Generator contract

Source: `vendor/Generator/`.

Weight: `stage2_final.pth`.

Use the supplied `TwoStageCVAE` with its checkpoint architecture: latent dimension 3, condition dimension 2, and a 20-by-50 output grid with normalized X and Y channels. Add the prescribed Z waterline positions when creating the point cloud. Keep the original checkpoint and supporting source together.

The integrated adapter uses the original model definition and trained parameters. The original `buildship.py`, `Test_Supercarrier.py` and optimization `infer_ship.py` are retained for traceability. The supported entry is the root launcher and the integrated workflow, which does not execute those demonstration scripts. New application code supplies bounded search, file allocation, physical-unit conversion and consistent export handling.

Generated output uses a full-width user parameter but a half-width coordinate extent. Preserve the realized hull shape when converting it to physical dimensions. Build the STL and preview from the same final point cloud used for volume evaluation and resistance prediction.

## Predictor contract

Source: `vendor/Predictor/`.

Weight: `prediction_best.pth`.

Inputs are a finite `1000 x 3` half-hull point cloud at `Xmax=3 m`, operating draft ratio `T/D`, and model speed in m/s. Output is total resistance in N. Use the full-depth cloud with a separate draft condition.

This uploaded checkpoint stores condition normalization, target normalization and a `log1p` target transform. Preserve them. Its inverse target transform is:

\[
R=\max\bigl(\exp(\hat y\sigma+\mu)-1,\;0\bigr).
\]

Use the checkpoint's actual architecture fields and saved normalizers. Do not substitute manuscript descriptions or a different training version. Do not recompute normalizers from an inference case.

The original reader is demonstrated by `vendor/Predictor/Branchmark/ship1.csv`. It has no header and contains 1000 XYZ points. The main application adds explicit format, scale and finite-value checks before inference. A cloud declared to be model scale must have Xmax within 0.2% of 3 m; the actual predictor input is then uniformly normalized to 3 m. A full-scale cloud's Xmax defines its length, and a separately supplied full length must agree within 0.2%.

The sparse-convolution runtime is part of this predictor. Treat GPU availability and sparse-convolution execution as runtime checks, not facts established solely by an environment package list.

## TD3 contract

Source and training configuration: `vendor/Hull_RL_Optimization/`.

Weight archive: `runs/td3/models/td3_final.zip`.

Preserve this observation order:

\[
[z_1,z_2,z_3,B/L,D/L,T/D,CB,V,R/R_0,e_\Delta,h].
\]

`R0` is the initial valid resistance of the current episode; it is not a user-supplied baseline. `e_delta` is the trained raw-grid displacement-error feature. `h` is the remaining fraction of the fixed episode horizon. The target resistance is an outer acceptance criterion and is not an additional observation component.

Preserve the three bounded actions and latent update:

\[
z_{k+1}=\operatorname{clip}(z_k+0.01a_k,-5,5),
\qquad a_k\in[-1,1]^3.
\]

The supplied configuration uses five steps per episode. The integrated loader reads `policy.pth` from the TD3 archive using tensor-only loading, selects its `actor.mu.` parameters and loads them into the matching PyTorch network: `11 -> 256 -> 256 -> 3`, with ReLU hidden activations and a Tanh output. This preserves the actor computation without deserializing historical Stable-Baselines3/cloudpickle training objects across Python versions. It does not restore training callbacks, replay buffers or optimizer states.

Optimization defaults to 100 episodes. Each episode allows up to 20 initial-latent trials, followed by at most five policy steps after successful initialization. It keeps the lowest-resistance physically feasible candidate encountered and can stop at the first feasible candidate below the target. Generation uses a separate default budget of 200 latent attempts. Budgets are finite; neither routine guarantees an acceptable candidate for every requested condition.

The nominal training-configuration ranges are:

| Quantity | Range |
| --- | --- |
| Model length | 3 m |
| `B/L` | 0.15 to 0.25 |
| `D/L` | 0.07 to 0.17 |
| `T/D` | 0.35 to 0.60 |
| Raw conditioning `CB` | 0.10 to 0.50 |
| Model speed | 0.6 to 1.8 m/s |

These are configured sampling ranges, not evidence of uniform training coverage or an accuracy guarantee. The original initialization rejects some sampled cases, and some combinations of independent ranges may be physically infeasible.

The user's 90 m example with `T=5.6 m` and `D=7.5 m` has `T/D≈0.7467`. Mark this as outside the TD3 configured draft-ratio range. Keep that fact visible in an optimization report.

## Result interpretation

Keep the requested ship's main output geometry at its physical scale, and keep the predictor's input geometry at the 3 m model scale. Save their relationship with the result. State the model speed after all conversions.

Accept a resistance-target success only after the exported candidate passes the relevant physical-volume and geometry checks and its predicted model resistance is below the target. If the target is missed, return the lowest-resistance feasible candidate actually found within the search budget. If none is feasible, report failure with the reason.

The predictor supplies a learned estimate. The application verifies dimensions, file integrity, mesh closure and orientation, and its own consistency checks. It does not run a general mesh self-intersection test or independently establish the hydrodynamic accuracy of a particular generated design.

## Sources

- User-supplied `Generator`, `Predictor`, `Hull_RL_Optimization` archives and `environment.yml`: authoritative sources for this release's model and runtime contracts.
- [ITTC High Speed Marine Vehicles – Resistance Test, 2002 Revision 01, Section 2.1](https://www.ittc.info/media/2065/75-02-05-01.pdf): used here for the Froude-number definition. The speed conversion above is derived by equating model and ship Froude numbers; this citation is not a claim that the document is the latest testing standard.
- [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/): matching PyTorch 2.5.1, torchvision 0.20.1 and CUDA 12.1 wheel installation.
- [spconv CUDA 12.1, version 2.3.8](https://pypi.org/project/spconv-cu121/2.3.8/) and [cumm CUDA 12.1, version 0.7.11](https://pypi.org/project/cumm-cu121/0.7.11/): available runtime distributions.
