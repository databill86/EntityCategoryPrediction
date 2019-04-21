# Category prediction model (Work in progress)

This repo contains AllenNLP model for prediction of Named Entity categories by its mentions.

# Data

## Fake data

You can generate some fake data using this [Notebook](notebooks/gen_face_data.ipynb)


## Real data (Work in progress)

Filtered [OneShotWikilinks](https://www.kaggle.com/generall/oneshotwikilinks) dataset with manually selected categories.


# Install

```bash
pip install -r requirements.txt
```

# Run


## Train

```bash

rm -rf ./data/vocabulary ; allennlp make-vocab -s ./data/ allen_conf.json --include-package category_prediction -o '{"vocabulary": {"directory_path": null}}'

allennlp train -f -s data/stats allen_conf.json --include-package category_prediction
```

## Validate

```bash
allennlp evaluate ./data/stats/model.tar.gz ./data/fake_data_test.tsv --include-package category_prediction
```

