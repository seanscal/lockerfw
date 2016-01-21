# LockrHub Capstone Firmware

### Running the application

To run the firmware application, simply call `make run` from the command line. This will install all python requirements and start the application.

> Ensure that python and pip are installed locally

### Testing the application

Once the application is running, you can test basic functionality by using the `curl` command from the command line.

For GET commands:

```
curl localhost:5000/test
```

For POST commands:

```
curl -H "Content-Type: application/json" -X POST -d '{"username":"xyz","password":"xyz"}' localhost:5000/test2
```


