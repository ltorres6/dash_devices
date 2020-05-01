import asyncio
import json
import quart

def serialize(obj):
    if hasattr(obj, 'to_plotly_json'):
        res = serialize(obj.to_plotly_json())
    elif isinstance(obj, dict):
        res = {}
        for key in obj:
            res[key] = serialize(obj[key])
    elif isinstance(obj, list) or isinstance(obj, tuple):
        res = []
        for i in obj:
            res.append(serialize(i))
    else:
        return obj
    return res


class Pusher:

    def __init__(self, server):
        self.server = server
        self.clients = []
        self.loop = None
        self.url_map = {}

        # websocket connection handler 
        @self.server.websocket('/_push')
        async def update_component_socket():
            print('**** spawning')
            if self.loop is None:
                self.loop = asyncio.get_event_loop()
            queue = asyncio.Queue()
            self.clients.append(queue)
            socket_sender = asyncio.create_task(quart.copy_current_websocket_context(self.socket_sender)(queue))
            socket_receiver = asyncio.create_task(quart.copy_current_websocket_context(self.socket_receiver)())
            try:
                await asyncio.gather(socket_sender, socket_receiver)
            finally:
                self.clients.remove(queue)
                print('*** exitting')


    async def socket_receiver(self):
        print('*** ws receive')
        try:
            while True:
                data = await quart.websocket.receive()
                data = json.loads(data);
                # Create new task so we can handle more messages, keep things snappy.
                asyncio.create_task(quart.copy_current_websocket_context(self.dispatch)(data))
        except asyncio.CancelledError:
            raise
        finally:
            print("*** ws receive exit")


    async def socket_sender(self, queue):
        print('*** ws send', queue)
        try:
            while True:
                mod = await queue.get()
                try:
                    json_ = json.dumps(mod)
                except TypeError:
                    json_ = json.dumps(serialize(mod)) 
                await quart.websocket.send(json_)
        except asyncio.CancelledError:
            raise
        finally:
            print("*** ws send exit")


    async def dispatch(self, data):
        index = data['url']
        if index.startswith('/'):
            index = index[1:]
        print('*** url', index, data['data'])
        func = self.url_map[index]
        output = await func(data['data'])
        # copy id into reply message
        output = {'id': data['id'], 'data': output}
        try:
            json_ = json.dumps(output)
        except TypeError:
            json_ = json.dumps(serialize(output)) 
        await quart.websocket.send(json_)

    def add_url(self, url, callback):
        self.url_map[url] = callback

    async def send(self, id_, data, client=None):
        message = {'id': id_, 'data': data}

        # send by putting in event loop
        # Oddly, push_nowait doesn't get serviced right away, so we use asyncio.run_coroutine_threadsafe
        if client is None: # send to all clients
            for client in self.clients:
                await client.put(message)
        else:
            await client.put(message)
        