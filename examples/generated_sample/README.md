# Real generator example

These artifacts were produced by the included `stage2_final.pth` using the integrated generation workflow on CPU. They are an execution example, not a resistance prediction or a validated hydrodynamic design.

| Input | Value |
| --- | --- |
| Length / full beam / molded depth | 90 / 15.6 / 7.5 m |
| Draft | 5.6 m |
| Requested displacement | 5000 metric tonnes |
| Water density | 1025 kg/m³ |
| Physical-volume tolerance for this check | 0.5% |
| Random seed | 42 |

The final CSV yields **4884.700424603554 m³** at the requested draft, corresponding to **5006.817935218643 t** and a relative displacement error of **+0.1363587044%**. The complete hull mesh has 3858 triangular faces, no boundary edges, and no nonmanifold edges. General mesh self-intersection testing was not performed.

Open [DesignCaseShip.html](DesignCaseShip.html) for the interactive, self-contained point-cloud view or [DesignCaseShip.png](DesignCaseShip.png) for the static preview. [DesignCaseShip.csv](DesignCaseShip.csv) is the half hull; [DesignCaseShip.stl](DesignCaseShip.stl) is the full hull. Both use metres.

[sample_result.json](sample_result.json) contains the measured result and latent/condition values. Its artifact paths were made relative to this folder for portability. This file is named differently from a normal case's `result.json`, so an agent will not mistake the bundled example for a newly completed user request. The geometry files and numeric measurements are unchanged. [search_history.csv](search_history.csv) records the real condition evaluations.

To reproduce using the Windows runtime, run the following from your desired output folder and substitute the installed project path:

```powershell
& 'D:\Tools\LLM4Ship\run.cmd' generate --length 90 --beam 15.6 --depth 7.5 --draft 5.6 --displacement-tonnes 5000 --density 1025 --volume-tolerance 0.005 --seed 42 --device cpu
```

Floating-point kernels on a different platform can change the realized values slightly. The recorded latent vector and raw condition in `sample_result.json` identify this particular candidate. Its draft ratio is outside the TD3 configuration's nominal range; no TD3 exploration was performed for this example.
