#for this file to run you need to have a config.yaml file in the same directory with the required parameters
#also make sure you download and extract the whole zip file from the repo to call the function of generating key words which is in main.py 


import yaml
import json
import pandas as pd
from schemas import SEMInputs
from main import generate_sem_plan  


def main():
    # 1. This will load config file
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    # 2. This will take the input
    inputs = SEMInputs(**config)

    # 3. we already made an existing file as main from there call this function and get the output
    result = generate_sem_plan(inputs)

    # 4. saving to the json file 
    with open("output_keywords.json", "w") as f:
        json.dump(result.dict(), f, indent=2)

    print("✅ Keywords saved to output_keywords.json")

    
if __name__ == "__main__":
    main()
