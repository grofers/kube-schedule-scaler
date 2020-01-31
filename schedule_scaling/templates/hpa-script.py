import pykube
import operator
import time
import datetime

def get_kube_api():
    try:
        config = pykube.KubeConfig.from_service_account()
    except FileNotFoundError:
        # local testing
        config = pykube.KubeConfig.from_file(os.path.expanduser('~/.kube/config'))
    api = pykube.HTTPClient(config)
    return api


api = get_kube_api()

minReplicas = %(minReplicas)s
maxReplicas = %(maxReplicas)s


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
            print('HPA %(name)s has been adjusted to minReplicas to %(minReplicas)s at', %(time)s)
        else:
            print('Something went wrong... HPA %(name)s has not been scaled')


    if maxReplicas != None:
        hpa.obj["spec"]["maxReplicas"] = maxReplicas
        hpa.update()

        if hpa.obj["spec"]["maxReplicas"] == maxReplicas:
            print('HPA %(name)s has been adjusted to maxReplicas to %(maxReplicas)s at', %(time)s)
        else:
            print('Something went wrong... HPA %(name)s has not been scaled')
