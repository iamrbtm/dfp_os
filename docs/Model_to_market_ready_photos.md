System Context & Goal:
I am building an AI marketing photo generator for my dfpos application (a Python-based point-of-sale and management tool). The feature generates photorealistic product photos from 3D models using an isolated, containerized Python microservice (FastAPI + Hugging Face Diffusers ControlNet Depth).

The target environment for the microservice is a 2013 Mac Pro (Trashcan, dual AMD FirePro), so it must run on CPU/MPS with aggressive memory optimization.

Key Architectural Requirements:

    Photo Checklist Integration: Instead of generic shot types, the generation process must hook directly into dfpos's existing Photo Checklist.

    S3 Storage: Returned images must be uploaded to our existing S3 Object Service, and the resulting S3 key/URL must be linked to that specific shot item in the checklist.

Please analyze the codebase and implement this end-to-end flow.
Phase 1: AI Microservice (ai-render-service)

Create an isolated microservice directory with a Dockerfile and requirements.txt.

    Framework: FastAPI + Hugging Face diffusers (runwayml/stable-diffusion-v1-5 and lllyasviel/sd-controlnet-depth).

    Hardware Optimizations: Configure PyTorch for cpu fallback (or mps with cpu error catching). Apply enable_model_cpu_offload(), enable_attention_slicing(), and torch.float32.

    Endpoint (POST /generate):

        Payload: Accepts depth_image (Base64), prompt (constructed from the checklist shot description), and shot_id / metadata.

        Output: Returns the generated image as a Base64 string along with passing back the shot_id.

Phase 2: Photo Checklist & S3 Integration (dfpos Application)

Examine the dfpos codebase to locate:

    The Photo Checklist data model/UI components.

    The S3 Object Service client implementation.

    The 3D Viewer module.

Implementation Steps:

    Checklist Trigger: Add a "Generate with AI" action directly to items within the existing Photo Checklist.

    Depth Extraction: When triggered for a specific checklist shot, set the 3D viewer angle according to that shot's requirements (if defined) and capture the Z-depth map as a Base64 string.

    Microservice Call: Post the depth map and the checklist shot parameters to the local microservice (http://localhost:<port>/generate).

    S3 Upload & Linking:

        Once the microservice returns the generated image, pass the image data to the existing S3 Object Service.

        Upload the image to the S3 bucket under a path like renders/{model_id}/{shot_id}.jpg.

        Update the Photo Checklist item in dfpos to attach the S3 image URL/key, marking the checklist item as completed or storing it as the shot preview.

    Non-Blocking UX: Because CPU generation takes time, update the Photo Checklist UI to show a "Generating..." badge/spinner on the target shot item while preserving app usability.

Execution Instructions for OpenCode:

    @explore the codebase for:

        The Photo Checklist module (data structures, UI components, state management).

        The S3 Object Service client configuration and helpers.

        The 3D viewer rendering code.

    Provide a brief plan detailing which files you will create or modify, including how you will structure the S3 upload and checklist association.

    Wait for my approval before modifying or creating files.