# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: OpenMDW-1.1
"""Adapted from Spark /home/homer/Sandbox/ct/inference.py and NV-Reason-CT."""
MODEL_ID = 'nvidia/NV-Reason-CT'
MODEL_REVISION = '386b93e034983f6c1fc841a43833a1b6a0cd9c13'


class CTModel:
    def __init__(self):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor
        if not torch.cuda.is_available() or torch.version.hip:
            raise RuntimeError('NV-Reason-CT requires an NVIDIA CUDA GPU.')
        if torch.cuda.get_device_properties(0).total_memory < 48 * 1024 ** 3:
            raise RuntimeError('NV-Reason-CT requires at least 48 GiB GPU memory on one device.')
        self.torch = torch
        self.model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, revision=MODEL_REVISION,
            trust_remote_code=True, dtype=torch.bfloat16, attn_implementation='sdpa').eval().to('cuda')
        self.processor = AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION, trust_remote_code=True)

    def answer(self, path, region, prompt):
        messages = [{'role': 'user', 'content': [{'type': 'image'}, {'type': 'text', 'text': prompt}]}]
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        inputs = self.processor(text=text, images3d=[str(path)], anatomy_region=region, return_tensors='pt').to(self.model.device)
        with self.torch.inference_mode():
            ids = self.model.generate(**inputs, max_new_tokens=2048, do_sample=False, use_cache=True)
        return self.processor.batch_decode(ids[:, inputs.input_ids.shape[1]:],
            skip_special_tokens=True, clean_up_tokenization_spaces=False)[0]
