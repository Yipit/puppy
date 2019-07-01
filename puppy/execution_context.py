from .js_handle import ElementHandle, JSHandle


class ExecutionContext:
    def __init__(self, id_, origin, name, aux_data, session):
        self._id = id_
        self._origin = origin
        self._name = name
        self._aux_data = aux_data
        self._session = session

    def evaluate(self, expression):
        response = self._session.send('Runtime.evaluate',
                                      expression=expression,
                                      contextId=self._id)
        if 'value' in response['result']:
            return response['result']['value']
        elif response['result'].get('subtype') == 'node':
            return ElementHandle(response['result']['objectId'],
                                 response['result'].get('description'),
                                 self,
                                 self._session)
        else:
            return JSHandle(response['result']['objectId'],
                            response['result'].get('description'),
                            self,
                            self._session)

    def call_function_on(self, function, args, return_by_value=False):
        return self._session.send('Runtime.callFunctionOn',
                                  functionDeclaration=function,
                                  arguments=self._convert_args(args),
                                  executionContextId=self._id,
                                  returnByValue=return_by_value,
                                  awaitPromise=True)

    def _convert_args(self, args):
        to_return = []
        for arg in args:
            if hasattr(arg, '_object_id'):
                to_return.append({'objectId': arg._object_id})
            else:
                to_return.append({'value': arg})
        return to_return
