# Procurement Manager smoke tests

## Offline sample

From the catalog checkout, run `mn blueprint validate ./procurement_manager` and start the co-worker's **Simulation: GPU workstation quotes** sample in OtterDesk. The sample folder is `examples/procurement_case`; the assessor reads only its selected `procurement_case.json`. Inspect the workflow view: `assess_procurement_case` and `compare_purchase_options` should both depend on `build_purchase_evidence`, and `publish_purchase_decision_packet` should wait for the assessment and recommendation audit.

The packet should show Atlas at $34,500 due at order and $40,500 known 36-month cost; Cedar at $34,800 for both; Delta as a synthetic no-response after its fixture deadline. Cedar should be proposed with owner, Finance, Legal, and Security reviews pending. Four simulated review actions should appear in conversation, each naming the exact decision digest. The report and `approval-packet.md` must say Simulation and draft for review. A click records a human response but does not yet advance the case or create an order. Public-source refreshes should be zero for this mock case.

## Manual material review

Make a separate local input folder with `purchase_request.txt` and `procurement_case.json`. Set `mode` to `MANUAL`, give the case a new stable `case_id`, and include only actual selected quote fields with `evidence_ref` values that identify the uploaded documents. Run `mn blueprint run ./procurement_manager --set inputs.payload.input_folder=/absolute/path/to/selected/folder`. Confirm the packet states MANUAL, preserves unknown shipping/tax/support as unknown, blocks a quote that fails a mandatory specification, and labels the export draft. If no policy is loaded or confirmed, the case section must say `WAITING_FOR_USER`. The current runtime does not collect reviews or supplier replies for the same case, so this smoke test ends at a review packet.
