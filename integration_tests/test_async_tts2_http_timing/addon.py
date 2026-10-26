from ten_runtime import Addon, register_addon_as_extension


@register_addon_as_extension("test_async_tts2_http_timing")
class TimingAddon(Addon):
    def on_create_instance(self, ten_env, name, context):
        from .extension import TimingExtension
        ten_env.on_create_instance_done(TimingExtension(name), context)
