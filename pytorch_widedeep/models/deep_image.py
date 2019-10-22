import torch

from ..wdtypes import *

from .deep_dense import dense_layer

from torch import nn
from torchvision import models


def conv_layer(ni:int, nf:int, ks:int=3, stride:int=1, maxpool:bool=True,
    adaptiveavgpool:bool=False):
    layer = nn.Sequential(
        nn.Conv2d(ni, nf, kernel_size=ks, bias=True, stride=stride, padding=ks//2),
        nn.BatchNorm2d(nf, momentum=0.01),
        nn.LeakyReLU(negative_slope=0.1, inplace=True))
    if maxpool: layer.add_module('maxpool', nn.MaxPool2d(2, 2))
    if adaptiveavgpool: layer.add_module('adaptiveavgpool', nn.AdaptiveAvgPool2d(output_size=(1, 1)))
    return layer


class DeepImage(nn.Module):

    def __init__(self,
        pretrained:bool=True,
        resnet:int=18,
        freeze:Union[str,int]=6,
        head_layers:Optional[List[int]] = None,
        head_dropout:Optional[List[float]]=None,
        head_batchnorm:Optional[bool] = False):
        super(DeepImage, self).__init__()
        """
        Standard image classifier/regressor using a pretrained network
        freezing some of the  first layers (or all layers).

        I use Resnets which have 9 "components" before the last dense layers.
        The first 4 are: conv->batchnorm->relu->maxpool.

        After that we have 4 additional 'layers' (so 4+4=8) comprised by a
        series of convolutions and then the final AdaptiveAvgPool2d (8+1=9).

        The parameter freeze sets the last layer to be frozen. For example,
        freeze=6 will freeze all but the last 2 Layers and AdaptiveAvgPool2d
        layer. If freeze='all' it freezes the entire network.
        """

        self.head_layers = head_layers

        if pretrained:
            if resnet==18:
                vision_model = models.resnet18(pretrained=True)
            elif resnet==34:
                vision_model = models.resnet34(pretrained=True)
            elif resnet==50:
                vision_model = models.resnet50(pretrained=True)

            backbone_layers = list(vision_model.children())[:-1]

            if isinstance(freeze, str):
                frozen_layers = []
                for layer in backbone_layers:
                    for param in layer.parameters():
                        param.requires_grad = False
                    frozen_layers.append(layer)
                self.backbone = nn.Sequential(*frozen_layers)
            if isinstance(freeze, int):
                assert freeze < 8, "freeze' must be less than 8 when using resnet architectures"
                frozen_layers = []
                trainable_layers = backbone_layers[freeze:]
                for layer in backbone_layers[:freeze]:
                    for param in layer.parameters():
                        param.requires_grad = False
                    frozen_layers.append(layer)

                backbone_layers = frozen_layers + trainable_layers
                self.backbone = nn.Sequential(*backbone_layers)
        else:
            self.backbone = nn.Sequential(
                conv_layer(3, 64, 3),
                conv_layer(64, 128, 1, maxpool=False),
                conv_layer(128, 256, 1, maxpool=False),
                conv_layer(256, 512, 1, maxpool=False, adaptiveavgpool=True),
                )

        # the output_dim attribute will be used as input_dim when "merging" the models
        self.output_dim = 512

        if self.head_layers is not None:
            self.head = nn.Sequential()
            for i in range(1, len(head_layers)):
                self.head.add_module(
                    'dense_layer_{}'.format(i-1),
                    dense_layer(head_layers[i-1], head_layers[i], head_dropout[i-1], head_batchnorm)
                    )
            self.output_dim = head_layers[-1]

    def forward(self, x:Tensor)->Tensor:
        x = self.backbone(x)
        x = x.view(x.size(0), -1)
        if self.head_layers is not None:
            out = self.head(x)
            return out
        else:
            return x