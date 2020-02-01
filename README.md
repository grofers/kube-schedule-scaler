# Kubernetes Schedule Scaler

This Application/ Kubernetes controller is used to schedule scale Horizontal Pod Autoscaler.
If hpa is configured the controller can adjust minReplicas and maxReplicas.
At the moment it supports reading the scaling definitions from:
  - directly in the annotations


## Usage


Just add the annotation to your `Horizontal Pod Autoscaler`.
```
  annotations:
    kube-schedule-scaler/schedule-actions: '[{"schedule": "10 18 * * *", "replicas": "3"}]'
```

## Available Fields 

The following fields are available
* `schedule` - Typical crontab format
* `replicas` - the number of replicas to scale to
* `minReplicas` - in combination with an `hpa` will adjust the `minReplicas` else be ignored
* `maxReplicas` - in combination with an `hpa` will adjust the `maxReplicas` else be ignored

### HorizontalPodAutoscaler Example

```bash
apiVersion: autoscaling/v1
kind: HorizontalPodAutoscaler
metadata:
  annotations:
    kube-schedule-scaler/schedule-actions: '[{"schedule": "53 18 * * *", "minReplicas": "3"}]'
  labels:
    app: hello-kubernetes
  name: hello-kubernetes
spec:
  maxReplicas: 10
  minReplicas: 1
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: hello-kubernetes
  targetCPUUtilizationPercentage: 70
status:
  currentCPUUtilizationPercentage: 0
  currentReplicas: 2
  desiredReplicas: 2
```




## Debugging

If your scaling action has not been executed for some reason, you can check with the below steps:

```bash
kubectl get pod | grep kube-schedule
kube-schedule-scaler-75644b8f79-h59s2                    1/1       Running                 0          3d
```


<p align="center">
<img src="img/pods.png" alt="Pods" title="Pods" />
</p>


Check for specific deployment at specific time
```bash
kubectl logs kube-schedule-scaler-87f9649f5-btnt7 | grep nginx-deployment-2 | grep "28-12-2018 09:50"
Deployment nginx-deployment-2 has been scaled successfully to 4 replica at 28-12-2018 09:50 UTC
```

You can also check from scalyr side
```bash
$application == "kube-schedule-scaler" 'nginx-deployment-2'
```
