import torch
from rdkit import RDLogger

# Suppress annoying RDKit warnings globally
RDLogger.DisableLog("rdApp.*")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
