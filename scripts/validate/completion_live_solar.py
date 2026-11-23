"""Bounded three-city live retest after payload/semantic guards; existing records never replaced."""
import argparse
from scripts.validate import final_solar_agent as runner
def run():
    runner.OUT=runner.ROOT/"docs/completion-20261123/live-solar"
    runner.run()
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--live",action="store_true");a=p.parse_args()
    if not a.live:p.error("--live is required for paid provider calls")
    run()
