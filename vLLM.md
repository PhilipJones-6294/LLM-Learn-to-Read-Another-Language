docker stop gemma4
docker rm gemma4

docker run -itd --name gemma4 \
    --ipc=host \
    --network host \
    --shm-size 32G \
    --gpus all \
    -v /home/pjones/llm_models/gemma-4-31b-nvfp4:/models/gemma4 \
    vllm/vllm-openai:gemma4-cu130 \
    /models/gemma4 \
    --max-model-len 65536 \
    --gpu-memory-utilization 0.40 \
    --host 0.0.0.0 \
    --port 8000


docker logs -f gemma4

python reader.py --host 0.0.0.0 --port 5001