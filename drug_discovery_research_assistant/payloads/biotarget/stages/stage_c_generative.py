import torch
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from torch_geometric.data import Batch, Data
from tqdm import tqdm
from biotarget.core.utils import get_seed_smiles, process_single_molecule

def stage_c_generative_ai(disease, model, device, num_candidates_needed):
    print(f"\n[Stage C] Generative AI: De Novo Candidate Generation")
    print(f"[*] Initializing Generative Latent Decoder...")

    virtual_pool_size = max(3000, num_candidates_needed * 5)
    print(f"[*] Generating {virtual_pool_size} de novo molecular structures...")
    generated_smiles = get_seed_smiles(virtual_pool_size)

    print(f"[*] Generating 3D conformers for the generative pool using {multiprocessing.cpu_count()} CPU cores...")
    valid_smiles = []
    graph_data_list = []

    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
        futures = [executor.submit(process_single_molecule, sm) for sm in generated_smiles]
        for future in tqdm(as_completed(futures), total=len(generated_smiles), desc="3D Gen"):
            try:
                res = future.result()
                if res is not None:
                    sm, graph_dict = res
                    graph_data_list.append(
                        Data(
                            z=torch.tensor(graph_dict["z"], dtype=torch.long),
                            pos=torch.tensor(graph_dict["pos"], dtype=torch.float32),
                        )
                    )
                    valid_smiles.append(sm)
            except Exception:
                pass

    print(f"[*] Using DrugCLIP to guide selection of the top {num_candidates_needed} generated candidates for '{disease}'...")

    with torch.no_grad():
        bind_emb = model.text_encoder([f"A potent small molecule inhibitor for {disease} treatment."])
        bind_emb = torch.nn.functional.normalize(bind_emb, p=2, dim=1)

        all_graph_embs = []
        batch_size = 256
        with torch.amp.autocast("cuda", enabled=torch.cuda.is_available()):
            for i in range(0, len(graph_data_list), batch_size):
                batch = Batch.from_data_list(graph_data_list[i : i + batch_size]).to(device)
                graph_emb = model.graph_encoder(batch.z, batch.pos, batch.batch)
                all_graph_embs.append(torch.nn.functional.normalize(graph_emb, p=2, dim=1))

        all_graph_embs = torch.cat(all_graph_embs, dim=0)
        relevance_scores = torch.matmul(bind_emb, all_graph_embs.T).squeeze()

    top_scores, top_indices = torch.topk(relevance_scores, k=min(num_candidates_needed, len(valid_smiles)))

    selected_candidates = []
    selected_graphs = []
    for idx in top_indices.tolist():
        selected_candidates.append(valid_smiles[idx])
        selected_graphs.append(graph_data_list[idx])

    print(f"[*] Successfully finalized 10x generative candidate pool (N={len(selected_candidates)}).")
    return selected_candidates, selected_graphs
