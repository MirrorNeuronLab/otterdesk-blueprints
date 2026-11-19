MIT License

Copyright (c) 2026 MirrorNeuronLab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Third-party materials

The tracker settings are adapted from the NVIDIA DeepStream reference
application, and the generated Multi-View 3D Tracking protobuf binding comes
from the same source snapshot. They retain [NVIDIA's Apache-2.0 notice](https://github.com/NVIDIA-AI-IOT/deepstream_reference_apps/blob/9946965e8adb1aa93b1b66983ec4196351c9190c/LICENSE).
The PeopleNet parser retains its NVIDIA MIT notice in the source file. The
DeepStream and Isaac Sim images and the PeopleNet model are fetched from
NVIDIA during the build.

The bundled Atrium stage, hotel sign and authored walk animation come from the
hotel scene in the Spark reference checkout. This blueprint adapts the stage
with the two reception exits and moves the guest rigs and cameras for live use.

The stage references furniture and decor by NVIDIA from its
[SimReady asset collection](https://huggingface.co/datasets/nvidia/simready-assets/tree/21b045a878e13d4ca922f0f8ebc2ff1e84bb06d4),
licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
and the F_Business_02 character from NVIDIA's Isaac Sim People library. The
[asset lock](payloads/isaac/assets/vendor_assets.json) identifies the exact
upstream files downloaded when the worker image is built. NVIDIA provides the
character and runtime under the [Isaac Sim licensing terms](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/common/license-faq.html).

The [G2 OmniPicker](https://huggingface.co/datasets/agibot-assets/simready-assets/blob/b0628c2800bb1d64559489d6b2b8643b0d502fcc/g2_omnipicker/simready_usd/g2_omnipicker.usda)
is AGIBOT's SimReady asset under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0). The
[asset lock](payloads/isaac/assets/agibot_assets.json) pins the original USD
layers. The Atrium composition gives the robot a travel pose and an optical
tag for camera-based localization.
