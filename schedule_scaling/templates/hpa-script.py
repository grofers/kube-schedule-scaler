import pykube
import operator
import time
import datetime
import requests
import os
import traceback

METRIC_SUCCESS = 0
METRIC_FAIL = 1

def push_metrics(name, namespace, resource, value):
    if 'PUSH_GATEWAY_URL' in os.environ:
        try:
            kube_schedule_scaler_failed_metric = (
                'kube_schedule_scaler_failed{{name="{name}",namespace="{namespace}",type="{resource}"}} {value}').format(name=name, namespace=namespace, resource=resource, value=str(value))
            requests.post(os.environ['PUSH_GATEWAY_URL'], data=kube_schedule_scaler_failed_metric)
        except Exception:
            traceback.print_exc()
            print('Something went wrong while pushing metrics')

def get_kube_api():
    try:
        config = pykube.KubeConfig.from_service_account()
    except FileNotFoundError:
        # local testing
        config = pykube.KubeConfig.from_file(os.path.expanduser('~/.kube/config'))
    api = pykube.HTTPClient(config)
    return api


api = get_kube_api()
deployment = pykube.Deployment.objects(api).filter(namespace="%(namespace)s").get(name="%(deployment_name)s")

replicas = %(replicas)s
minReplicas = %(minReplicas)s
maxReplicas = %(maxReplicas)s

if replicas != None:
    deployment.replicas = replicas
    deployment.update()

    if deployment.replicas == replicas:
        push_metrics(name="%(name)s", namespace="%(namespace)s", resource="deployment", value=METRIC_SUCCESS)
        print('Deployment %(deployment_name)s has been scaled successfully to %(replicas)s replica at', %(time)s)
    else:
        push_metrics(name="%(name)s", namespace="%(namespace)s", resource="deployment", value=METRIC_FAIL)
        print('Something went wrong... deployment %(deployment_name)s has not been scaled')


try:
    hpa = pykube.HorizontalPodAutoscaler.objects(api).filter(namespace="%(namespace)s").get(name="%(name)s")
except Exception as e:
    print('HPA for deployment %(name)s in namespace %(namespace)s not found: {}'.format(e))
    hpa = None

if hpa:
    if minReplicas != None:
        hpa.obj["spec"]["minReplicas"] = minReplicas
        hpa.update()

        if hpa.obj["spec"]["minReplicas"] == minReplicas:
            push_metrics(name="%(name)s", namespace="%(namespace)s", resource="hpa", value=METRIC_SUCCESS)
            print('HPA %(name)s has been adjusted to minReplicas to %(minReplicas)s at', %(time)s)
        else:
            push_metrics(name="%(name)s", namespace="%(namespace)s", resource="hpa", value=METRIC_FAIL)
            print('Something went wrong... HPA %(name)s has not been scaled')


    if maxReplicas != None:
        hpa.obj["spec"]["maxReplicas"] = maxReplicas
        hpa.update()

        if hpa.obj["spec"]["maxReplicas"] == maxReplicas:
            push_metrics(name="%(name)s", namespace="%(namespace)s", resource="hpa", value=METRIC_SUCCESS)
            print('HPA %(name)s has been adjusted to maxReplicas to %(maxReplicas)s at', %(time)s)
        else:
            push_metrics(name="%(name)s", namespace="%(namespace)s", resource="hpa", value=METRIC_FAIL)
            print('Something went wrong... HPA %(name)s has not been scaled')
