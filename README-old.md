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

Introducing Checkbin, an visualization SDK focused on speed and simplicity. Follow our guide below to run your first trace.

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

```
import checkbin

checkbin.authenticate(token=os.environ["CHECKBIN_TOKEN"])

checkbin_app = checkbin.App(app_key="my_first_app")
```

## Concepts

### Trace

A trace is a single execution of your application. A trace has inputs, passes a series of checkins, and ends with an output. It is the fundamental unit of observation in Checkbin.

### Checkins

If a trace follows a path through your application, checkins are the guide markers along the way. You'll place checkins at critical junctures in your code where it's important to record the current state.

### Sets

Of course, it's not enough to trace your application with just one input. That's where sets come in. Sets are a simple way to query many inputs at once to run through your application.

### Run

A run is a collection of traces. You'll use runs to observe the behavior of your application across many inputs and isolate failure cases.

## Integration

### Create a input set

In order to run your first trace, you'll need an input set. Any valid JSON can be used to create your set. Files are a special kind of input data that can be visualized in our run explorer later.

[Create Set](https://app.checkbin.dev/dashboard/input-sets)

If you prefer to create your sets programmatically, our SDK has you covered.

```
set = checkbin_app.create_input_set(name="My First Input Set")

for row in input_data:
    new_input = set.add_input()
    new_input.add_state(key="model_blend", value=row.model_blend)
    new_input.add_file(key="url", url=row.file_url)

set_id = set.submit()
```

Even simpler still, you can invoke the `start_run` method in the next section with a path to a CSV or JSON file. We'll take care of the rest.

### Bins

Once you've created your set, copy the set id. You'll use this to initialize your first run. Runs are executed in a context manager. This allows us to track trace failures and log error messages.

```
with checkbin_app.start_run(set_id="a46dab01-7a79-4eef-ab0c-2131d6ff92b2") as bins:
```

After you start a run, you'll receive a list of objects called bins. Think of each bin as the state manager for a single trace. You'll use your bin to query input data, mark checkins, and submit your trace.

```
for bin in bins:
    model_blend = bin.get_input_data("model_blend")
    file_url = bin.get_input_file_url("file")

    your_app.main(model_blend=model_blend, file_url=file_url, bin=bin)

```

### Checkins

Checkins are the backbone of your traces in Checkbin. They allow you to mark the state of your application at a particular juncture. We've designed our SDK to make checkins simple to use. To create a checkin, simply name it.

```
bin.checkin(name="My First Checkin")
```

From this point onwards, you can think of your bin as state storage for that checkin. If there's a state you want to store in "My First Checkin", just call one of our two state helper functions.

```
bin.add_state(name="model_param_1", value=model_param_1)
```

Remember, files are a special kind of input data that can be visualized in our run explorer later.

```
bin.add_file(name="intermediate_image", url=file_url)
```

Copying the same upload code over and over can be a hassle. We've got you covered. Your Checkbin account automatically comes with 5GB of cloud storage. Just call `upload_file` from your bin.

```
bin.upload_file(name="my-file", file_path="path/to/file")
```

In our projects, we've found ourselves reusing code to upload Python images as files, so we've added a helper function for that too.

```
bin.upload_image(name="image-mask", image=pil_image)
```

Once you're finished with your first checkin and are ready for the next, create another just as before. Checkbin will handle the rest.

```
bin.checkin(name="My Second Checkin")
bin.add_state(name="model_param_2", value=model_param_2)
```

### Submitting your trace

The final step for your first trace is submission. Once you've added all of the states you want for your final checkin, simply call `submit`. It's that simple!

```
bin.submit()
```
