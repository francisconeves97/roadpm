# RoadPM: Road traffic pattern mining

This work contains code to apply biclustering for mining traffic patterns of road mobility, a subject remaining largely unexplored up to date. 

## Installation:

Python 3+

All dependencies defined in **requirements.txt**. You can install them by:

```
$ conda create --name <env> python=3.7
$ conda activate <env>
$ pip install -r requirements.txt
```

## Usage:

After installing the required dependencies and activating your freshly created environment you should be able to run our app. 

You can see our interface for querying road traffic data by running and accessing http://127.0.0.1:8051/:

```
$ python roadpm.py
```

You can test our solution by using the example data available at the `data/` folder. First you should run the interface and access http://127.0.0.1:8050/:

```
$ python roadpm_from_csv.py
```

After accessing the interface choose to upload a file, then navigate to `data/` and choose `example-dataset.csv`.

---

 Please cite: contributions currently under review, contact Rui Henriques (rmch@tecnico.ulisboa.pt) or Francisco Neves (francisco.neves@tecnico.ulisboa.pt) to obtain the updated reference.

 Guidelines to access data are available upon request

