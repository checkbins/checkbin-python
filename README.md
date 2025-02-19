# Checkbin

[![PyPI - Version](https://img.shields.io/pypi/v/checkbin.svg)](https://pypi.org/project/checkbin)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/checkbin.svg)](https://pypi.org/project/checkbin)

---

## Table of Contents

- [Installation](#installation)
- [License](#license)
- [Introduction](#introduction)
- [Getting Started](#getting-started)
- [Concepts](#concepts)
- [Integration](#integration)

## Installation

```console
pip install checkbin
```

## License

`checkbin` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.

## Introduction

Introducing Checkbin, a visualization SDK focused on speed and simplicity. Checkbin helps you create comparison grids directly from your code, eliminating the need for manual image editing tools. Follow our guide below to create your first comparison grid.

## Getting Started

### Create your first app

To get started, create a Checkbin account with the link below. All you need is an email.

[Signup](https://app.checkbin.dev/sign-up)

After you've created your account, make your first app! This is as simple as clicking the "Create App" button on your dashboard. After your app is created, you'll want to copy your app key for use in the SDK later.

Finally, get your Checkbin account token in settings.

### Install the SDK

To install the SDK, run the following command:

```
pip install checkbin
```

You'll want to use your account token and app key from earlier to initialize the SDK.

```python
import checkbin

checkbin.authenticate(token=os.environ["CHECKBIN_TOKEN"])

checkbin_app = checkbin.App(app_key="my_first_app")
```

## Concepts

### The Comparison Grid

At its core, Checkbin helps you create comparison grids. Think of it like a spreadsheet where:
- Each row represents a different input or test case
- Each column represents a step in your process
- Each cell can contain images, data, or other variables you want to track

### Rows (formerly Bins)

A row represents a single test case or input in your comparison grid. Each row follows a path through your application, collecting data and images at each step. You'll create rows for each input you want to analyze.

### Columns (formerly Checkins)

If a row represents a path through your application, columns are the checkpoints along that path. You place columns at critical points in your code where you want to record the current state, images, or other data.

### Sets

Sets are collections of inputs that you want to analyze together. When you create a grid, you'll typically use a set to define what inputs should be processed (i.e., what rows should be created).

### Rows (formerly Run)

A Rows object represents a collection of test cases in your analysis. Each Row represents a different input or test case, and each Column represents a checkpoint in your process. Together, they form a comparison grid that gives you a comprehensive view of how your application behaves across different inputs.

## Integration

### Create an input set

Before creating your comparison grid, you'll need an input set. This defines what rows will appear in your grid. Any valid JSON can be used to create your set. Files are a special kind of input data that can be visualized in our grid explorer later.

[Create Set](https://app.checkbin.dev/dashboard/input-sets)

If you prefer to create your sets programmatically, our SDK has you covered:

```python
set = checkbin_app.create_input_set(name="My First Input Set")

for input_data in dataset:
    new_input = set.add_input()
    new_input.add_state(key="model_blend", value=input_data.model_blend)
    new_input.add_file(key="url", url=input_data.file_url)

set_id = set.submit()
```

Even simpler still, you can invoke the `create_rows` method in the next section with a path to a CSV or JSON file. We'll take care of the rest.

### Creating Rows

Once you've created your set, copy the set id. You'll use this to initialize your comparison grid. Grids are created in a context manager, which allows us to track failures and log error messages.

```python
with checkbin_app.create_rows(set_id="a46dab01-7a79-4eef-ab0c-2131d6ff92b2") as rows:
```

After you create the rows, you'll receive a collection of row objects. Each row manages the state for a single test case. You'll use your row to query input data, add columns, and record state.

```python
for row in rows:
    # Get input data for this row
    model_blend = row.get_input_data("model_blend")
    file_url = row.get_input_file_url("file")

    # Process the input and record results
    your_app.main(model_blend=model_blend, file_url=file_url, row=row)
```

### Creating Columns

Columns are the backbone of your comparison grid. They allow you to mark the state of your application at particular points. Creating a column is as simple as naming it:

```python
row.checkin(name="Step 1: Initial Processing")
```

From this point onwards, you can think of your row as state storage for that column. If there's data you want to store in "Step 1", just call one of our state helper functions:

```python
row.add_state(name="model_param_1", value=model_param_1)
```

Files (like images) are a special kind of data that can be visualized in our grid explorer:

```python
row.add_file(name="intermediate_image", url=file_url)
```

Copying the same upload code over and over can be a hassle. We've got you covered. Your Checkbin account automatically comes with 5GB of cloud storage. Just call `upload_file` from your row:

```python
row.upload_file(name="my-file", file_path="path/to/file")
```

For Python images, we've added a special helper:

```python
row.upload_image(name="image-mask", image=pil_image)
```

When you're ready to move to the next column, simply create another one just as before:

```python
row.checkin(name="Step 2: Final Output")
row.add_state(name="model_param_2", value=model_param_2)
```

### Submitting your grid

The final step is submission. Once you've added all the data you want for your final column, simply call `submit`:

```python
row.submit()
```

### Alternative: Using Factories

If you need more control over row creation, you can use the row factory pattern:

```python
# Create a factory for generating rows
factory = app.create_row_factory(run_name="My Analysis")

# Create a row with specific input state
row = factory.get_row(
    input_state={"model_blend": 0.5},
    input_files={"image": "https://example.com/input.jpg"}
)

# Process the row as before
row.checkin(name="Step 1")
row.add_state(name="output", value=result)
row.submit()
```

## Legacy API

Note: For backward compatibility, all the original method names are still available:
- `Rows` was formerly called `Checkbin`
- `Row` was formerly called `Bin`
- `Column` was formerly called `Checkin`
- `create_rows()` was formerly called `start_run()`
- `create_row_factory()` was formerly called `create_bin_factory()`

The original names will continue to work, but we recommend using the new, more intuitive names for better code readability.