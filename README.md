# RespAgent
Multimodal Multi-Agent Systems for Responsive Front-End Code Generation


## Overview
We propose AgentGen+, a multi-agent framework for responsive web page generation, and introduce a benchmark dataset and evaluation metrics for assessing cross-resolution fidelity and consistency. Across six screen resolutions, AgentGen+ significantly outperforms both single-reference and multi-reference baselines (p < 0.001), achieving the highest overall quality and reducing cross-resolution variability by 17%.

## Set Up
This project is managed using `uv`. Run the following command to install dependencies:

```
uv sync
```

To enable screenshot capture and metadata generation, install Playwright:

```
playwright install
```

## Datasets
The full dataset contains 357 responsive web pages, along with screenshots and metadata for experiments.

You can download it from: [Google Drive (281MB)](https://drive.google.com/file/d/1iQuzvkWHxNmLgaDbdjec5Qa5uXwxmV_c/view?usp=sharing). After downloading, unzip the dataset and place it in the project root directory.

After downloading, unzip the dataset and place it in the project root directory.

### Manual Dataset Preparation (Optional)

Instead of downloading the dataset archive, you can also build the dataset manually by following steps.

1. Start a web server:
```
python scripts/web_server.py
```
2. Unzip HTML files:
```
python -m scripts.datasets unzip
``` 
3. Generate screenshots and metedata:
```
python -m scripts.datasets metadata
``` 

## Experiments

### Generate HTML Files
This project uses LiteLLM to interact with foundation models for HTML generation and feedback.

It supports 100+ LLMs. See the full list in: [LiteLLM Documents](https://docs.litellm.ai/).

Using the `multi_agent` script to generate HTML file with different approaches.

```
python -m multi_agent [OPTIONS]
```
General Options:
```
-h, --help            show this help message and exit
--prompt PROMPT       Prompt type to process (single or multi, default: multi)
--feedback FEEDBACK   Feedback type to process (gen or spec)
--model MODEL         Model to use for generation (default: gpt-5.1-codex-mini)
--count COUNT         Number of files to process (default: all)
--file FILE           Specific file name to process (e.g., 62.html)
--iter ITER           Number of iterations for revision (default: 1)
--version VERSION     Number of versions to generate (default: 1)
--focus              Whether to focus on revision based on feedback (default: False)
```

Example Usage:
* `python -m multi_agent --count 1`: Generate one HTML file using the default model without feedback.
* `python -m multi_agent --prompt single --model gemini/gemini-3-flash-preview --file 62.html`: Generate a specific file using a different model and single-reference prompting.

Experiment Configurations:
* `SingleRef`:
```
python -m multi_agent --prompt single
```

* `MultiRef`
```
python -m multi_agent --prompt multi
```

* `AgentSpec`
```
python -m multi_agent --prompt multi --feedback spec
```

* `AgentGen`
```
python -m multi_agent --prompt multi --feedback gen
```

* `AgentGen+`
```
python -m multi_agent --prompt multi --feedback gen --focus
```

### Evaluate
Use `scripts.evaluate` to evaluate generated HTML files.
Results are saved in `results/scores` as `.csv` files.

```
python -m scripts.evaluate --model MODEL_NAME [--version VERSION]
```
General Options:
```
-h, --help         show this help message and exit
--model MODEL      Model to use for generation (default: gpt-5.1-codex-mini)
--version VERSION  Version of the generated HTML to evaluate (default: 1)
```

Generate score files for all approaches in version 1:
```
python -m scripts.evaluate
```

### Report
Use `scripts.report` to generate experiment reports.
Outputs are saved in `results/report` as `.tex` files.

```
python -m scripts.report --model MODEL_NAME [--version VERSION]
```
General Options:
```
-h, --help         show this help message and exit
--model MODEL      Model to use for generation (default: gpt-5.1-codex-mini)
--version VERSION  Max version of the generated HTML to include in the report (default: 1)
```

Generate reports for all approaches in version 1:
```
python -m scripts.report
```

## License
The code and dataset are released for research purposes only.
Please do not use them for malicious or harmful activities.

This dataset is built upon the [Design2Code](https://salt-nlp.github.io/Design2Code/) dataset and follows the ODC Attribution License (ODC-By).

## Acknowledgement

Our dataset is derived from the [Design2Code](https://salt-nlp.github.io/Design2Code/). We sincerely thank the authors for their excellent work.

We welcome contributions of all kinds.
If you have questions or suggestions, feel free to contact us.