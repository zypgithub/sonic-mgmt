import tempfile
import json
import os


class SwssContainer:
    @staticmethod
    def apply_config(engine, config_dict, asic_id_extension=''):
        with tempfile.NamedTemporaryFile(suffix=".json", prefix="config", mode='w') as fp:
            json.dump(config_dict, fp)
            fp.flush()

            # Copy JSON config to switch
            dst_dir = "/tmp"
            file_name = next(tempfile._get_candidate_names()) + ".json"
            engine.copy_file(source_file=fp.name, dest_file=file_name, file_system=dst_dir,
                             overwrite_file=True, verify_file=False)

            # Copy JSON config inside swss container
            cmd = "docker cp {} swss{}:/".format(os.path.join(dst_dir, file_name), asic_id_extension)
            engine.run_cmd(cmd)

            # Apply config in swss container
            cmd = "docker exec -i swss{} swssconfig /{}".format(asic_id_extension, file_name)
            engine.run_cmd(cmd)
