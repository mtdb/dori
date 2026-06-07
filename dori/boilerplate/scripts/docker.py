import json
import sys

ANSWERS = {
    "remove a container": (
        "docker rm <container_id>\n"
        "  Force-remove a running container: docker rm -f <container_id>\n"
        "  Remove all stopped containers:    docker container prune"
    ),
    "list running containers": (
        "docker ps\n  List all containers (including stopped): docker ps -a"
    ),
    "list containers": (
        "docker ps\n  List all containers (including stopped): docker ps -a"
    ),
    "show containers": (
        "docker ps\n  List all containers (including stopped): docker ps -a"
    ),
    "stop a container": (
        "docker stop <container_id>\n"
        "  Stop all running containers: docker stop $(docker ps -q)"
    ),
    "stop all containers": ("docker stop $(docker ps -q)"),
    "list images": ("docker images\n  Or: docker image ls"),
    "remove an image": (
        "docker rmi <image_id>\n"
        "  Force-remove: docker rmi -f <image_id>\n"
        "  Remove all unused images: docker image prune -a"
    ),
    "run a container": (
        "docker run <image>\n"
        "  Run in background (detached): docker run -d <image>\n"
        "  Map a port:                   docker run -p 8080:80 <image>"
    ),
    "view container logs": (
        "docker logs <container_id>\n  Follow live logs: docker logs -f <container_id>"
    ),
    "exec into a container": (
        "docker exec -it <container_id> bash\n"
        "  Use 'sh' if bash is not available: docker exec -it <container_id> sh"
    ),
    "build an image": (
        "docker build -t <name>:<tag> .\n"
        "  No cache:           docker build --no-cache -t <name>:<tag> .\n"
        "  Custom Dockerfile:  docker build -f Dockerfile.prod -t <name> ."
    ),
    "inspect a container": ("docker inspect <container_id>"),
    "copy files to container": (
        "docker cp <local_path> <container_id>:<container_path>"
    ),
    "copy files from container": (
        "docker cp <container_id>:<container_path> <local_path>"
    ),
    "restart a container": ("docker restart <container_id>"),
    "pause a container": (
        "docker pause <container_id>\n  Unpause: docker unpause <container_id>"
    ),
    "show container stats": ("docker stats"),
    "pull an image": ("docker pull <image>:<tag>"),
    "push an image": ("docker push <image>:<tag>"),
    "tag an image": ("docker tag <source_image> <target_image>:<tag>"),
    "prune everything": (
        "docker system prune\n  Include volumes: docker system prune --volumes"
    ),
}


def find_answer(question: str) -> str | None:
    q = question.lower().strip()
    if q in ANSWERS:
        return ANSWERS[q]
    for key, answer in ANSWERS.items():
        if all(word in q for word in key.split()):
            return answer
    return None


def main():
    if len(sys.argv) < 2:
        print("Error: Missing JSON payload", file=sys.stderr)
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
        question = payload.get("question", "")
        raw_text = payload.get("raw_text", "")

        answer = find_answer(question) if question else None

        if not answer and raw_text:
            answer = find_answer(raw_text)
            question = raw_text

        if answer:
            print(f"🐳 [Docker] {question.capitalize()}:\n  {answer}")
        else:
            display = question or raw_text or "unknown"
            print(
                f"🐳 [Docker]: No built-in answer for '{display}'. "
                "Try: docker help or https://docs.docker.com"
            )

    except json.JSONDecodeError:
        print("Error: Invalid JSON payload provided to docker script.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
