import argparse

from app.core.config import settings
from app.knowledge.retrieval import retrieve_observations
from app.knowledge.store import FashionKnowledgeStore
from app.services.integration_tools.llm import LLM
from app.services.styling_agent import StylingAgent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the text-only styling planner demo.")
    parser.add_argument("request", help="Natural-language outfit request")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--no-revision", action="store_true")
    args = parser.parse_args()

    store = FashionKnowledgeStore(settings.article_data_dir)
    observations = retrieve_observations(args.request, store.observations(), args.top_k)
    agent = StylingAgent(LLM())
    result = agent.run(args.request, observations, revise_once=not args.no_revision)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
