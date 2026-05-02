import yaml
from pathlib import Path

def test_docker_compose_volume_mounts_scorecard():
    """T044: test docker-compose.yml volume config covers scorecard path"""
    compose_path = Path(__file__).parent.parent.parent / "docker-compose.yml"
    assert compose_path.exists()
    
    with open(compose_path, "r", encoding="utf-8") as f:
        compose_dict = yaml.safe_load(f)
        
    core_volumes = compose_dict.get("x-core-service", {}).get("volumes", [])
    
    # We want to ensure that /app/data is mounted because scorecard path is data/validation/scorecards
    # Check if there's a volume mapping to /app/data
    found = False
    for v in core_volumes:
        if isinstance(v, str) and ":/app/data" in v:
            found = True
            break
    
    assert found, "docker-compose.yml x-core-service must mount /app/data to access scorecards"
