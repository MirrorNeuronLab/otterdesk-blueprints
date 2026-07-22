def stage_e_reporting(disease, evaluation_results, top_ligands, report_path=None):
    print(f"\n[Stage E] Reporting")

    max_aff = max([r["gnina_affinity"] for r in evaluation_results])
    min_aff = min([r["gnina_affinity"] for r in evaluation_results])

    for r in evaluation_results:
        r["norm_binding"] = (r["gnina_affinity"] - min_aff) / (max_aff - min_aff + 1e-8)
        r["final_score"] = r["norm_binding"] - (0.5 * r["tox_penalty"])

    ranked_results = sorted(
        evaluation_results, key=lambda x: x["final_score"], reverse=True
    )

    print("\n" + "=" * 85)
    print(f"BIOTARGET PIPELINE FINAL RESULTS FOR: '{disease}'")
    print("=" * 85)
    print(
        f"{'Rank':<5} | {'Final':<6} | {'Gnina (pK_d)':<12} | {'Tox Penalty':<13} | {'SMILES'}"
    )
    print("-" * 85)

    report_lines = [
        "## Stage E: Final Ranking\n",
        "| Rank | Final Score | Gnina (pK_d) | Tox Penalty | SMILES |\n",
        "|------|-------------|--------------|-------------|--------|\n",
    ]

    for rank in range(min(top_ligands, len(ranked_results))):
        r = ranked_results[rank]
        f_score = r["final_score"]
        gnina_aff = r["gnina_affinity"]
        t_score = r["tox_penalty"]

        tox_flag = "⚠️ HIGH" if t_score > 0.7 else "OK"
        print(
            f"#{rank + 1:<4} | {f_score:.4f} | {gnina_aff:.4f} ({r['norm_binding']:.2f}) | {t_score:.4f} {tox_flag:<7} | {r['smiles'][:35]}..."
        )

        report_lines.append(
            f"| #{rank + 1} | {f_score:.4f} | {gnina_aff:.4f} ({r['norm_binding']:.2f}) | {t_score:.4f} {tox_flag} | `{r['smiles']}` |\n"
        )

    if report_path:
        with open(report_path, "a") as f:
            f.writelines(report_lines)
